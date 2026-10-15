"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { StatusPill } from "@/components/ui/StatusPill";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiResult, Closing, Page } from "@/lib/api/types";
import { saveBlob } from "@/lib/download";
import { describeClosingError } from "@/lib/expense-labels";
import { cashBookHref, monthPackageHref } from "@/lib/api/statement";
import { formatDateLong, formatDayLong } from "@/lib/format";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { areasFor } from "@/lib/permissions";
import { currentLocalPeriod, periodLabel, recentPeriods } from "@/lib/statement-labels";

/** O mes anterior a `period` (YYYY-MM). */
function previousMonth(period: string): string {
  return recentPeriods(period, 2)[1] ?? period;
}

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="px-5 py-4 sm:px-6">
      <dt className="text-sub text-ink-2">{label}</dt>
      <dd className="mt-0.5 text-[1.125rem] font-bold tabular-nums text-brand-800 sm:text-[1.25rem]">{value}</dd>
      {note && <dd className="mt-0.5 text-foot text-ink-2 [overflow-wrap:anywhere]">{note}</dd>}
    </div>
  );
}

interface ClosingCardProps {
  schoolId: string;
  closing: Closing;
  permissions: string[];
  open: boolean;
  onToggle: () => void;
  onChanged: (message: string) => void;
}

function ClosingCard({ schoolId, closing: c, permissions, open, onToggle, onChanged }: ClosingCardProps) {
  const areas = areasFor(permissions);
  const canVerify = permissions.includes("statement:read");
  const canPdf = permissions.includes("reports:read") || permissions.includes("reports:read_aggregate");
  const reopened = c.reopenedAt !== null;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  async function verify() {
    setBusy("verify");
    setError(null);
    setNotice(null);
    const r = await api.closings.verify(schoolId, c.id);
    setBusy(null);
    if (!r.ok) return setError(describeClosingError(r.error));
    setNotice(
      r.data.verified
        ? "Verificado: os lançamentos do mês batem com este fechamento."
        : "Não confere: os lançamentos do mês não batem mais com este fechamento. Avise a administração.",
    );
  }

  async function pdf() {
    setBusy("pdf");
    setError(null);
    setNotice(null);
    const r = await api.closings.pdf(schoolId, c.id);
    setBusy(null);
    if (!r.ok) return setError(describeClosingError(r.error));
    saveBlob(r.data.blob, `extrato-mensal-${c.period}.pdf`);
    setNotice("PDF do extrato mensal gerado.");
  }

  async function reopen() {
    const text = reason.trim();
    if (text.length < 10 || text.length > 500) return setReasonError("Explique o motivo com 10 a 500 caracteres.");
    setReasonError(null);
    setBusy("reopen");
    setError(null);
    const r = await api.closings.reopen(schoolId, c.id, text);
    setBusy(null);
    if (!r.ok) return setError(describeClosingError(r.error));
    setReopening(false);
    setReason("");
    onChanged(`Fechamento de ${periodLabel(c.period)} reaberto.`);
  }

  return (
    <li data-status={reopened ? "reopened" : "closed"} className="overflow-hidden rounded-[var(--r-lg)] border border-line bg-white">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-5 sm:px-8 sm:py-6">
        <div className="min-w-0 flex-1 basis-56">
          <p className="text-[1.0625rem] font-semibold capitalize leading-snug text-brand-800 sm:text-[1.25rem]">{periodLabel(c.period)}</p>
          <p className="text-sub text-ink-2">
            Saldo em caixa <span className="tabular-nums">{formatBRL(c.closingBalanceCents)}</span> · fechado em {formatDateLong(c.closedAt)}
          </p>
        </div>
        <StatusPill tone={reopened ? "warning" : "success"}>{reopened ? "Reaberto" : "Fechado"}</StatusPill>
        <Button variant="chip" size="md" aria-expanded={open} aria-label={`${open ? "Fechar" : "Abrir"} o fechamento de ${periodLabel(c.period)}`} onClick={onToggle} className="min-h-12 w-full px-8 sm:w-auto">
          {open ? "Fechar" : "Ver"}
        </Button>
      </div>

      {open && (
        <div className="border-t border-line px-5 py-6 sm:px-8 sm:py-8" data-testid="closing-detail">
          <dl className="grid divide-y divide-line overflow-hidden rounded-[var(--r-lg)] border border-line sm:grid-cols-2 sm:divide-y-0 sm:[&>div:nth-child(n+3)]:border-t sm:[&>div:nth-child(even)]:border-l sm:[&>div]:border-line">
            <Row label="Saldo inicial" value={formatBRL(c.openingBalanceCents)} />
            <Row
              label="Entradas"
              value={formatBRL(c.totalInCents)}
              note={`Contribuições ${formatBRL(c.contributionsInCents)} · outras ${formatBRL(c.otherInCents)} · devoluções recebidas ${formatBRL(c.refundsInCents)}`}
            />
            <Row label="Total de saídas" value={formatBRL(c.totalOutCents)} note={`Despesas ${formatBRL(c.expensesOutCents)} · reembolsos ${formatBRL(c.reimbursementsOutCents)}`} />
            <Row label="Saldo em caixa no fechamento" value={formatBRL(c.closingBalanceCents)} note="Saldo principal." />
            <Row
              label="Após reembolsos pendentes"
              value={formatBRL(c.closingAfterPendingCents)}
              note={`Menos ${formatBRL(c.pendingReimbursementsCents)} de reembolsos ainda a pagar.`}
            />
            <Row label="Lançamentos" value={String(c.entriesCount)} />
            <Row
              label="Saldo informado pelo banco"
              value={c.bankBalanceReportedCents === null ? "Não informado" : formatBRL(c.bankBalanceReportedCents)}
              note={c.bankDifferenceCents === null ? undefined : `Diferença (banco menos caixa): ${formatBRL(c.bankDifferenceCents)}`}
            />
            <Row label="Código de verificação" value={`${c.entriesHash.slice(0, 16)}…`} note={c.entriesHash} />
          </dl>

          {reopened && (
            <p role="note" className="mt-4 rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
              Este fechamento foi reaberto em {formatDateLong(c.reopenedAt!)}: <strong className="font-semibold">não tem PDF nem verificação</strong>. Para ter de novo, feche o mês outra vez.
              {c.reopenReason ? ` Motivo: ${c.reopenReason}` : ""}
            </p>
          )}

          <div aria-live="polite">
            {error && !reopening && <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}
            {notice && <p role="status" className="mt-4 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            {!reopened && canPdf && (
              <Button size="md" onClick={() => void pdf()} disabled={busy !== null} aria-busy={busy === "pdf"} className="min-h-12 rounded-full! px-7">
                {busy === "pdf" ? "Gerando…" : "Baixar PDF do extrato mensal"}
              </Button>
            )}
            {!reopened && canVerify && (
              <Button size="md" variant="secondary" onClick={() => void verify()} disabled={busy !== null} aria-busy={busy === "verify"} className="min-h-12 rounded-full! px-7">
                {busy === "verify" ? "Verificando…" : "Verificar"}
              </Button>
            )}
            {!reopened && areas.reopenMonths && (
              <Button size="md" variant="plain" aria-expanded={reopening} onClick={() => setReopening((v) => !v)} className="min-h-12 rounded-full! px-7">
                Reabrir mês
              </Button>
            )}
          </div>

          <FormModal
            open={reopening && !reopened && areas.reopenMonths}
            title="Reabrir mês"
            intro="Reabrir só vale para o último fechamento e fica registrado com o seu nome e o motivo."
            onClose={() => setReopening(false)}
            busy={busy === "reopen"}
          >
            <form
              method="post"
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                void reopen();
              }}
              className="space-y-5"
            >
              <TextField label="Motivo da reabertura" name="reopen-reason" autoComplete="off" maxLength={500} hint="De 10 a 500 caracteres." value={reason} onChange={(e) => setReason(e.target.value)} error={reasonError ?? undefined} />
              <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
              <FormButtons onCancel={() => setReopening(false)} cancelLabel="Voltar" submitLabel="Reabrir o fechamento" pendingLabel="Reabrindo…" pending={busy === "reopen"} />
            </form>
          </FormModal>
        </div>
      )}
    </li>
  );
}

function CloseMonthForm({ schoolId, permissions, suggestion, onClosed }: { schoolId: string; permissions: string[]; suggestion: string; onClosed: (closing: Closing) => void }) {
  const [latest] = useState(() => currentLocalPeriod());
  // Meses que ja acabaram: do anterior ao atual para tras. A API decide a ordem e se o mes terminou.
  const options = recentPeriods(previousMonth(latest), 36);
  const [period, setPeriod] = useState(options.includes(suggestion) ? suggestion : options[0]!);
  const [open, setOpen] = useState(false);
  const [cents, setCents] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fromStatement, setFromStatement] = useState<string | null>(null);

  /** O saldo do ultimo extrato OFX enviado ate o fim do mes escolhido (conciliacao). Preenche; a pessoa ainda confere. */
  async function fillFromStatement() {
    setFromStatement(null);
    const r = await api.reconciliation.closingBalance(schoolId, period);
    if (!r.ok) return setFromStatement("Não foi possível buscar o saldo do extrato. Digite o valor.");
    if (r.data.totalCents === null) return setFromStatement("Nenhum extrato enviado até o fim deste mês. Envie o extrato em Conciliação ou digite o valor.");
    setCents(r.data.totalCents > 0 ? r.data.totalCents : 0);
    setFromStatement(
      r.data.items.map((i) => `${i.nickname}: ${formatBRL(i.closingBalanceCents)} em ${formatDayLong(i.asOf)}`).join(" · ") +
        (r.data.totalCents <= 0 ? " (saldo zerado ou negativo: digite à mão, se precisar)" : ""),
    );
  }

  async function close() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const r = await api.closings.create(schoolId, cents > 0 ? { period, bankBalanceReportedCents: cents } : { period });
    setBusy(false);
    if (!r.ok) return setError(describeClosingError(r.error));
    setCents(0);
    setOpen(false);
    onClosed(r.data);
  }

  return (
    <div className="mb-8">
      <Button variant="chip" size="md" onClick={() => setOpen(true)} className="min-h-12 px-7">
        Fechar um mês
      </Button>
      <p className="mt-2 max-w-[60ch] text-sub text-ink-2">
        Os meses são fechados em ordem e só depois que terminam. O fechamento congela os números do mês e gera o código de verificação.
      </p>
      <FormModal
        open={open}
        title="Fechar mês"
        intro="O fechamento congela os números do mês e gera o código de verificação. Os meses são fechados em ordem e só depois que terminam."
        onClose={() => setOpen(false)}
        busy={busy}
      >
        <form
          method="post"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void close();
          }}
          className="space-y-5"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField id="close-period" label="Mês a fechar" value={period} onChange={(e) => setPeriod(e.target.value)}>
              {options.map((p) => (
                <option key={p} value={p}>
                  {periodLabel(p)}
                </option>
              ))}
            </SelectField>
            <TextField
              label="Saldo informado pelo banco"
              optional
              name="bank-balance"
              prefix="R$"
              inputMode="numeric"
              autoComplete="off"
              placeholder="0,00"
              hint="Para conferir com o caixa. A diferença aparece no fechamento."
              value={cents === 0 ? "" : formatBRLNumber(cents)}
              onChange={(e) => setCents(centsFromDigits(e.target.value))}
            />
          </div>
          {areasFor(permissions).manageReconciliation && (
            <div>
              <Button variant="plain" size="md" onClick={() => void fillFromStatement()} className="rounded-full!">
                Usar o saldo do extrato do banco
              </Button>
              {fromStatement && <p role="status" className="mt-2 text-sub text-ink-2">{fromStatement}</p>}
            </div>
          )}
          <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Fechar mês" pendingLabel="Fechando…" pending={busy} />
        </form>
      </FormModal>
    </div>
  );
}

/** O Livro Caixa do mes (planilha e PDF) e, so para a gestao, o pacote do mes (ZIP com o livro e os anexos). Sao downloads. */
function BookCard({ schoolId, management }: { schoolId: string; management: boolean }) {
  const [latest] = useState(() => currentLocalPeriod());
  const options = recentPeriods(latest, 36);
  const [period, setPeriod] = useState(options[0]!);
  const link = "inline-flex min-h-11 items-center rounded-full border border-line-strong bg-white px-5 text-sub font-semibold text-brand-800 hover:bg-bg";
  return (
    <section aria-label="Livro Caixa e pacote do mês" className="mb-8 rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
      <h2 className="text-heading">Livro Caixa e pacote do mês</h2>
      <p className="mt-1 max-w-[62ch] text-sub text-ink-2">
        O Livro Caixa lista tudo o que entrou e saiu, na ordem, com o saldo depois de cada lançamento.{management ? " O pacote reúne o livro e os anexos das despesas do mês, para entregar ao contador." : ""}
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <div className="min-w-0 basis-56">
          <SelectField id="book-period" label="Mês" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {options.map((p) => (
              <option key={p} value={p}>
                {periodLabel(p)}
              </option>
            ))}
          </SelectField>
        </div>
        <a className={link} href={cashBookHref(schoolId, period, "csv")} download>
          Livro Caixa (planilha)
        </a>
        <a className={link} href={cashBookHref(schoolId, period, "pdf")} download>
          Livro Caixa (PDF)
        </a>
        {management && (
          <a className={link} href={monthPackageHref(schoolId, period)} download>
            Pacote do mês (ZIP)
          </a>
        )}
      </div>
    </section>
  );
}

interface Props {
  schoolId: string;
  permissions: string[];
}

/**
 * Fechamento mensal REAL (docs/statement.md). Lista os fechamentos com o estado (fechado ou reaberto), mostra os
 * numeros congelados e o codigo de verificacao, verifica, baixa o PDF pela API (so de fechamento ativo) e,
 * para quem tem `months:close`, fecha o mes. Reabrir exige `months:reopen` (hoje so o administrador da
 * organizacao) e um motivo. O site so mostra o que a API devolve; ela decide a ordem dos meses.
 */
export function ClosingsArea({ schoolId, permissions }: Props) {
  const areas = areasFor(permissions);
  const [version, setVersion] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const key = `${schoolId}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<Page<Closing>> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.closings.list(schoolId, { limit: 50 }).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, key]);

  const res = loaded?.key === key ? loaded.res : null;
  const items = res && res.ok ? [...res.data.items].sort((a, b) => (a.period < b.period ? 1 : a.period > b.period ? -1 : a.closedAt < b.closedAt ? 1 : -1)) : [];
  const lastActive = items.find((c) => c.reopenedAt === null);
  // O mes seguinte ao ultimo fechamento ativo (quando nao ha, o formulario comeca no mes anterior ao atual).
  const next = lastActive ? nextMonth(lastActive.period) : "";

  return (
    <div>
      {/* So depois da lista: o mes sugerido (o seguinte ao ultimo fechamento ativo) precisa ser conhecido, e o
          formulario nao pode ser recriado, zerando a escolha da pessoa, quando a lista chegar. */}
      {areas.closeMonths && res && (
        <CloseMonthForm
          key={next}
          schoolId={schoolId}
          permissions={permissions}
          suggestion={next}
          onClosed={(c) => {
            setBanner(`Mês fechado: ${periodLabel(c.period)}.`);
            setOpenId(c.id);
            setVersion((n) => n + 1);
          }}
        />
      )}
      <BookCard schoolId={schoolId} management={areas.closeMonths} />
      {!areas.closeMonths && (
        <p role="note" className="mb-6 rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-brand-800">
          Você pode consultar os fechamentos e baixar o PDF. Fechar o mês é da gestão e da direção.
        </p>
      )}

      {banner && <p role="status" className="mb-4 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{banner}</p>}

      {!res && (
        <div role="status" aria-busy="true" aria-live="polite">
          <span className="sr-only">Carregando os fechamentos…</span>
          <div aria-hidden="true" className="rounded-[var(--r-lg)] border border-line p-6">
            <div className="skeleton h-4 w-48" />
            <div className="skeleton mt-4 h-10 w-full" />
          </div>
        </div>
      )}
      {res && !res.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {res.error.status === 403 ? "O seu perfil não vê os fechamentos desta escola." : describeClosingError(res.error)}
        </p>
      )}
      {res && res.ok && items.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-12 text-center">
          <h2 className="text-heading">Nenhum mês fechado ainda</h2>
          <p className="mx-auto mt-2 max-w-[44ch] text-body text-ink-2">Quando a gestão fechar um mês, o fechamento aparece aqui, com os números e o PDF.</p>
        </div>
      )}
      {items.length > 0 && (
        <ul aria-label="Fechamentos mensais" className="space-y-4">
          {items.map((c) => (
            <ClosingCard
              key={c.id}
              schoolId={schoolId}
              closing={c}
              permissions={permissions}
              open={openId === c.id}
              onToggle={() => setOpenId(openId === c.id ? null : c.id)}
              onChanged={(message) => {
                setBanner(message);
                setVersion((n) => n + 1);
              }}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** O mes seguinte a `period` (YYYY-MM). */
function nextMonth(period: string): string {
  const [year, month] = period.split("-").map(Number);
  if (!year || !month) return period;
  const index = year * 12 + month;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}
