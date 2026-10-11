"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Amount } from "@/components/ui/Amount";
import { Button, buttonClass } from "@/components/ui/Button";
import { ChevronDownThinIcon, ClockHistoryIcon, DownloadIcon, PencilSquareIcon, XLgIcon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import { contributionsPdfHref } from "@/lib/api/statement";
import type { ApiError, ApiResult, Page, PendingEntry, StatementEntry, StatementSummary } from "@/lib/api/types";
import { describeAuthError } from "@/lib/auth-messages";
import { sectionHref, type PainelSection } from "@/lib/painel-section";
import { KIND_LABELS, type MovementKind } from "@/lib/status";
import { PENDING_SECTIONS, periodLabel, pendingSectionTitle, recentPeriods, currentLocalPeriod } from "@/lib/statement-labels";
import { CashContributionForm } from "./CashContributionForm";
import { KIND_META } from "./kinds";
import { PendingRows, StatementList } from "./StatementList";
import { StatementIndicators } from "./StatementIndicators";

type Res<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "forbidden" } | { state: "error"; message: string };

function toRes<T>(result: ApiResult<T>): Res<T> {
  if (result.ok) return { state: "ready", data: result.data };
  if (result.error.status === 403) return { state: "forbidden" };
  return { state: "error", message: describeError(result.error) };
}

function describeError(error: ApiError): string {
  if (error.kind === "problem" && error.code === "validation_error") return "Esse mês não é válido.";
  return describeAuthError(error, "context");
}

const LOADING: Res<never> = { state: "loading" };

function Skeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="rounded-[var(--r-lg)] border border-line p-6">
        <div className="skeleton h-4 w-40" />
        <div className="skeleton mt-4 h-12 w-64 max-w-full" />
        <div className="skeleton mt-8 h-16 w-full" />
      </div>
    </div>
  );
}

function Notice({ tone, children }: { tone: "info" | "bad"; children: React.ReactNode }) {
  return (
    <p
      role={tone === "bad" ? "alert" : "note"}
      className={`rounded-[var(--r-md)] px-4 py-3 text-sub ${tone === "bad" ? "bg-bad-soft font-medium text-bad" : "bg-info-soft text-brand-800"}`}
    >
      {children}
    </p>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-[var(--r-lg)] border border-line px-6 py-12 text-center">
      <h2 className="text-heading">{title}</h2>
      <p className="mx-auto mt-2 max-w-[44ch] text-body text-ink-2">{text}</p>
    </div>
  );
}

interface PainelDataProps {
  /** `school.id` do vinculo ATIVO da sessao. Nunca vem de URL nem de campo do usuario. */
  schoolId: string;
  section: PainelSection;
  /** YYYY-MM vindo da URL; sem ele a API usa o mes corrente no fuso da escola. */
  period: string | undefined;
  permissions: string[];
  onPeriodChange: (period: string) => void;
}

/**
 * Numeros REAIS da escola do vinculo ativo (docs/statement.md): resumo do mes, lancamentos por tipo
 * (com "carregar mais"), pendencias fora do saldo e as acoes da tesouraria. Cada rota que responder 403
 * (perfil `viewer` so le o resumo) vira um aviso: a tela nao quebra.
 */
export function PainelData({ schoolId, section, period, permissions, onPeriodChange }: PainelDataProps) {
  const canReadStatement = permissions.includes("statement:read");
  const canRecordCash = permissions.includes("contributions:record_cash");
  const canReadReports = permissions.includes("reports:read") || permissions.includes("reports:read_aggregate");
  const kind: MovementKind | null = section === "resumo" ? null : section;

  const [reload, setReload] = useState(0);
  const [cashOpen, setCashOpen] = useState(false);
  const [latest] = useState(() => currentLocalPeriod());

  // Cada recurso guarda a chave do pedido que o gerou: chave diferente = ainda carregando (sem setState sincrono no efeito).
  const summaryKey = `${schoolId}|${period ?? ""}|${reload}`;
  const [summaryState, setSummaryState] = useState<{ key: string; res: Res<StatementSummary> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.statement.summary(schoolId, period).then((result) => {
      if (!cancelled) setSummaryState({ key: summaryKey, res: toRes(result) });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, summaryKey]);
  const summary: Res<StatementSummary> = summaryState?.key === summaryKey ? summaryState.res : LOADING;

  const entriesKey = `${schoolId}|${period ?? ""}|${kind ?? ""}|${reload}`;
  const [entriesState, setEntriesState] = useState<{ key: string; res: Res<Page<StatementEntry>> } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  useEffect(() => {
    if (!kind || !canReadStatement) return;
    let cancelled = false;
    void api.statement.entries(schoolId, { period, kind, limit: 50 }).then((result) => {
      if (!cancelled) setEntriesState({ key: entriesKey, res: toRes(result) });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, kind, canReadStatement, entriesKey]);
  const entries: Res<Page<StatementEntry>> = entriesState?.key === entriesKey ? entriesState.res : LOADING;

  async function loadMore() {
    if (entries.state !== "ready" || !entries.data.nextCursor || loadingMore) return;
    setLoadingMore(true);
    setMoreError(null);
    const result = await api.statement.entries(schoolId, { period, kind: kind ?? undefined, limit: 50, cursor: entries.data.nextCursor });
    setLoadingMore(false);
    if (!result.ok) {
      setMoreError(describeError(result.error));
      return;
    }
    setEntriesState({
      key: entriesKey,
      res: { state: "ready", data: { items: [...entries.data.items, ...result.data.items], nextCursor: result.data.nextCursor } },
    });
  }

  const pendingKey = `${schoolId}|${reload}`;
  const [pendingState, setPendingState] = useState<{ key: string; res: Res<Page<PendingEntry>> } | null>(null);
  useEffect(() => {
    if (section !== "resumo" || !canReadStatement) return;
    let cancelled = false;
    void api.statement.pending(schoolId, { limit: 100 }).then((result) => {
      if (!cancelled) setPendingState({ key: pendingKey, res: toRes(result) });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, section, canReadStatement, pendingKey]);
  const pending: Res<Page<PendingEntry>> = pendingState?.key === pendingKey ? pendingState.res : LOADING;

  const effectivePeriod = summary.state === "ready" ? summary.data.period : (period ?? null);
  const periods = effectivePeriod ? Array.from(new Set([...recentPeriods(latest, 12), effectivePeriod])).sort().reverse() : [];

  const divider = <span aria-hidden="true" className="hidden h-16 w-px self-center bg-line lg:block" />;
  const toolbar = (
    <div className="mb-7 flex flex-col gap-5 border-b border-line pb-7 sm:flex-row sm:flex-wrap sm:items-end sm:gap-x-8 sm:gap-y-5">
      {effectivePeriod && (
        <div>
          <label htmlFor="period-select" className="mb-2 block text-[1.0625rem] font-light text-ink sm:text-[1.25rem]">
            Mês
          </label>
          <div className="relative">
            <select
              id="period-select"
              value={effectivePeriod}
              onChange={(e) => onPeriodChange(e.target.value)}
              className={buttonClass("chip", "md", "min-h-12 w-full cursor-pointer appearance-none justify-start pl-6 pr-12 font-medium sm:w-64")}
            >
              {periods.map((p) => (
                <option key={p} value={p} className="bg-white text-ink">
                  {periodLabel(p)}
                </option>
              ))}
            </select>
            <ChevronDownThinIcon size={18} className="pointer-events-none absolute right-5 top-1/2 -translate-y-1/2 text-white" />
          </div>
        </div>
      )}
      {canRecordCash && (
        <>
          {divider}
          <div>
            <p className="mb-2 text-[1.0625rem] font-light text-ink sm:text-[1.25rem]">Contribuição</p>
            <Button variant="chip" size="md" aria-haspopup="dialog" onClick={() => setCashOpen(true)} className="min-h-12 w-full px-7 font-medium sm:w-auto">
              Contribuição em dinheiro
            </Button>
          </div>
        </>
      )}
      {canReadReports && summary.state === "ready" && (
        <>
          {divider}
          {/* Navegacao comum (o navegador baixa o PDF com o cookie de sessao); sem fetch nem blob. */}
          <a
            href={contributionsPdfHref(schoolId, summary.data.period)}
            download
            className={buttonClass("chip", "md", "min-h-12 px-7 font-medium sm:ml-auto")}
          >
            Baixar PDF{" "}
            <span className="sr-only">das contribuições do mês</span>
            <DownloadIcon size={16} />
          </a>
        </>
      )}
    </div>
  );

  return (
    <div>
      {toolbar}

      <Modal open={canRecordCash && cashOpen} onClose={() => setCashOpen(false)} label="Registrar contribuição em dinheiro">
        <CashContributionForm
          schoolId={schoolId}
          onRecorded={() => setReload((n) => n + 1)}
          onClose={() => setCashOpen(false)}
        />
      </Modal>

      {section === "resumo" && (
        <div className="space-y-8">
          {summary.state === "loading" && <Skeleton label="Carregando o resumo do mês…" />}
          {summary.state === "ready" && <StatementIndicators summary={summary.data} />}
          {summary.state === "forbidden" && <Notice tone="info">O seu perfil não tem acesso aos números desta escola.</Notice>}
          {summary.state === "error" && <Notice tone="bad">{summary.message}</Notice>}

          {!canReadStatement && summary.state === "ready" && (
            <Notice tone="info">
              O seu perfil vê só os totais do mês. Os lançamentos e as pendências são da tesouraria.
            </Notice>
          )}

          {canReadStatement && <PendingBlock pending={pending} />}
        </div>
      )}

      {kind && (
        <section aria-labelledby="kind-title">
          <h2 id="kind-title" className="sr-only">
            {KIND_META[kind].plural}
            {effectivePeriod ? ` de ${periodLabel(effectivePeriod)}` : ""}
          </h2>
          <Link href={sectionHref("resumo", period)} className="mb-3 inline-flex min-h-11 items-center text-sub font-semibold text-brand-800 underline underline-offset-2">
            Voltar ao dashboard
          </Link>
          <p className="mb-4 max-w-[60ch] text-body text-ink-2">{KIND_META[kind].definition}</p>
          {!canReadStatement && <Notice tone="info">O seu perfil não vê os lançamentos desta escola.</Notice>}
          {canReadStatement && entries.state === "loading" && <Skeleton label="Carregando os lançamentos…" />}
          {entries.state === "forbidden" && <Notice tone="info">O seu perfil não vê os lançamentos desta escola.</Notice>}
          {entries.state === "error" && <Notice tone="bad">{entries.message}</Notice>}
          {entries.state === "ready" &&
            (entries.data.items.length === 0 ? (
              <EmptyState
                title={`Nenhuma ${KIND_LABELS[kind].toLowerCase()} neste mês`}
                text={`Quando houver ${KIND_META[kind].plural.toLowerCase()} em ${effectivePeriod ? periodLabel(effectivePeriod) : "este mês"}, elas aparecem aqui, uma por linha, com o status de cada uma.`}
              />
            ) : (
              <>
                <StatementList entries={entries.data.items} label={KIND_META[kind].plural} />
                {moreError && (
                  <p role="alert" className="mt-3 text-sub font-medium text-bad">
                    {moreError}
                  </p>
                )}
                {entries.data.nextCursor && (
                  <div className="mt-4 text-center">
                    <Button variant="secondary" onClick={loadMore} disabled={loadingMore} aria-busy={loadingMore}>
                      {loadingMore ? "Carregando…" : "Carregar mais"}
                    </Button>
                  </div>
                )}
              </>
            ))}
        </section>
      )}
    </div>
  );
}

/** Ilustracao de cada tipo de pendencia (Figma); sem ilustracao, um icone no mesmo molde. */
const PENDING_MEDIA: Record<string, ReactNode> = {
  PAYABLE: <Image src="/brand/3d-cash.webp" alt="" width={256} height={197} className="h-auto w-12" />,
  AWAITING_APPROVAL: <Image src="/brand/3d-check.webp" alt="" width={256} height={261} className="h-auto w-12" />,
  AWAITING_CORRECTION: (
    <span className="grid size-12 place-items-center rounded-full bg-warn-soft text-warn">
      <PencilSquareIcon size={22} />
    </span>
  ),
  REVIEW: <Image src="/brand/3d-analysis.webp" alt="" width={256} height={256} className="h-auto w-12" />,
  RECEIVABLE: (
    <span className="grid size-12 place-items-center rounded-full bg-info-soft text-brand-800">
      <ClockHistoryIcon size={22} />
    </span>
  ),
};

function PendingBlock({ pending }: { pending: Res<Page<PendingEntry>> }) {
  const [openSection, setOpenSection] = useState<string | null>(null);
  if (pending.state === "loading") return <Skeleton label="Carregando as pendências…" />;
  if (pending.state === "forbidden") return <Notice tone="info">O seu perfil não vê as pendências desta escola.</Notice>;
  if (pending.state === "error") return <Notice tone="bad">{pending.message}</Notice>;

  const items = pending.data.items;
  const known = new Set(PENDING_SECTIONS.map((s) => s.section));
  // Cartoes do Figma: as 4 primeiras secoes sempre; "A receber" e "Outras" so quando houver. O total de cada cartao e
  // a soma dos valores (em centavos) das linhas que a API devolveu, so para o resumo; o detalhe abre ao clicar.
  const cards = [
    ...PENDING_SECTIONS.map((s, index) => ({ ...s, index, rows: items.filter((e) => e.section === s.section) })),
    { section: "OTHER", title: pendingSectionTitle("OTHER"), note: "", index: 99, rows: items.filter((e) => !known.has(e.section)) },
  ].filter((c) => c.index < 4 || c.rows.length > 0);
  const opened = cards.find((c) => c.section === openSection) ?? null;

  return (
    <section aria-labelledby="pending-title" className="rounded-[var(--r-lg)] border border-line p-5 sm:p-7">
      <h2 id="pending-title" className="text-[1.125rem] font-normal tracking-normal text-ink-2 sm:text-[1.375rem]">
        Pendências (fora do saldo)
      </h2>
      <p className="mt-0.5 text-foot text-ink-2">Nada daqui entra no saldo em caixa até ser pago ou confirmado.</p>

      <ul className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => {
          const total = card.rows.reduce((sum, row) => sum + row.amountCents, 0);
          const count = card.rows.length;
          return (
            <li key={card.section}>
              <button
                type="button"
                disabled={count === 0}
                aria-haspopup="dialog"
                onClick={() => setOpenSection(card.section)}
                className="flex w-full items-center gap-3 rounded-[1.25rem] border border-line-strong bg-white p-4 text-left transition-colors enabled:hover:bg-info-soft/50 disabled:cursor-default"
              >
                <span aria-hidden="true" className="grid h-12 w-12 shrink-0 place-items-center">
                  {PENDING_MEDIA[card.section]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sub font-light leading-tight text-ink">{card.title}</span>
                  <span className="mt-0.5 block text-[1.125rem] font-bold leading-tight text-brand-800 sm:text-[1.25rem]">
                    <Amount cents={total} symbolClassName="text-brand-800" />
                  </span>
                  <span className="block text-[0.75rem] text-ink-2">{count === 0 ? "Nenhum item" : count === 1 ? "1 item" : `${count} itens`}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {items.length === 0 && (
        <p className="mt-5 text-body text-ink-2">
          <strong className="font-semibold text-ink">Nenhuma pendência</strong>. Quando houver algo a pagar, a conferir ou a receber, aparece aqui.
        </p>
      )}
      {pending.data.nextCursor && (
        <p className="mt-4 text-foot text-ink-2">Há mais pendências do que as mostradas aqui: os totais acima cobrem só as exibidas.</p>
      )}

      <Modal open={opened !== null} onClose={() => setOpenSection(null)} label={opened?.title ?? "Pendências"}>
        {opened && (
          <div className="px-5 pb-8 pt-6 sm:px-10 sm:pb-10 sm:pt-9">
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-[clamp(1.5rem,1.1rem+1.2vw,2rem)] font-semibold leading-tight">{opened.title}</h2>
              <button
                type="button"
                onClick={() => setOpenSection(null)}
                aria-label="Fechar a janela"
                className="-mr-2 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink-3 hover:bg-info-soft"
              >
                <XLgIcon size={22} />
              </button>
            </div>
            {opened.note && <p className="mt-1 max-w-[60ch] text-body text-ink-2">{opened.note}</p>}
            <div className="mt-6">
              <PendingRows entries={opened.rows} label={opened.title} />
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
}
