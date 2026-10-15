"use client";

import { useEffect, useRef, useState } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { StatusPill } from "@/components/ui/StatusPill";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { AccountPurpose, ApiError, ApiResult, BankAccount, BankLine, LedgerEntry, Reconciliation, StatementImport } from "@/lib/api/types";
import { formatDayLong } from "@/lib/format";
import { formatBRL } from "@/lib/money";
import { areasFor } from "@/lib/permissions";

const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi alterado.";
const KIND_LABELS: Record<string, string> = { CONTRIBUTION: "Contribuição", EXPENSE: "Despesa", REIMBURSEMENT: "Reembolso", REFUND: "Devolução" };

/** Os textos de erro do envio do extrato (a API manda so o codigo). */
function describeError(error: ApiError, fallback = "Não foi possível concluir. Tente de novo."): string {
  if (error.kind === "network" || error.kind === "timeout") return NETWORK;
  if (error.status === 413) return "O arquivo é grande demais. O limite é de 2 MB.";
  switch (error.code) {
    case "not_an_ofx_file":
      return "Este arquivo não é um extrato OFX. No site do seu banco, exporte o extrato no formato OFX.";
    case "ofx_without_lines":
      return "O extrato não tem nenhum lançamento.";
    case "ofx_line_unreadable":
    case "ofx_unreadable":
      return "Não conseguimos ler um dos lançamentos do arquivo. Exporte o extrato de novo.";
    case "ofx_too_many_lines":
      return "O extrato tem lançamentos demais. Exporte um período menor (até 5.000 lançamentos).";
    case "already_imported":
      return "Este arquivo já foi enviado antes.";
    case "account_inactive":
      return "Esta conta está desligada. Escolha outra.";
    case "permission_denied":
      return "Você não tem permissão para mexer na conciliação.";
    case "conflict":
      return "Já existe uma conta com esse apelido.";
    default:
      return fallback;
  }
}

const Card = ({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) => (
  <section className="rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-heading">{title}</h2>
      {action}
    </div>
    {children}
  </section>
);

/**
 * Conciliacao: as contas onde a escola recebe, o envio do extrato OFX do banco e a comparacao com o caixa em quatro
 * listas. So leitura: nada e lancado no caixa por aqui. Quem decide o pareamento e a API (certeza ou divergencia).
 */
export function ReconciliationArea({ schoolId, permissions }: { schoolId: string; permissions: string[] }) {
  const allowed = areasFor(permissions).manageReconciliation;
  const [version, setVersion] = useState(0);
  const key = `${schoolId}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; accounts: ApiResult<BankAccount[]>; imports: ApiResult<StatementImport[]> } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    void Promise.all([api.reconciliation.accounts(schoolId), api.reconciliation.imports(schoolId)]).then(([accounts, imports]) => {
      if (!cancelled) setLoaded({ key, accounts, imports });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, key, allowed]);

  if (!allowed) {
    return (
      <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
        O seu perfil não mexe na conciliação desta escola.
      </p>
    );
  }
  if (!loaded) {
    return (
      <div role="status" aria-busy="true">
        <span className="sr-only">Carregando a conciliação…</span>
        <div aria-hidden="true" className="skeleton h-32 w-full" />
      </div>
    );
  }
  const accounts = loaded.accounts.ok ? loaded.accounts.data : [];
  const imports = loaded.imports.ok ? loaded.imports.data : [];
  const reload = () => setVersion((n) => n + 1);

  return (
    <div className="space-y-6">
      <p className="max-w-[64ch] text-body text-ink-2">
        Compare o extrato do banco com o caixa do sistema. Aqui você só <strong className="font-semibold text-ink">confere</strong>: nada é lançado no caixa.
      </p>
      {!loaded.accounts.ok && <p role="alert" className="text-sub font-medium text-bad">{describeError(loaded.accounts.error)}</p>}
      <AccountsCard schoolId={schoolId} accounts={accounts} onChanged={reload} />
      <ImportCard
        schoolId={schoolId}
        accounts={accounts.filter((a) => a.isActive)}
        onImported={(imported) => {
          setOpenId(imported.id);
          reload();
        }}
      />
      <Card title="Extratos enviados">
        {imports.length === 0 ? (
          <p className="text-body text-ink-2">Nenhum extrato enviado ainda. Envie o primeiro acima.</p>
        ) : (
          <ul aria-label="Extratos enviados" className="space-y-3">
            {imports.map((item) => {
              const account = accounts.find((a) => a.id === item.bankAccountId);
              const isOpen = openId === item.id;
              return (
                <li key={item.id} className="rounded-[var(--r-md)] border border-line">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="font-semibold text-brand-800">
                        {formatDayLong(item.periodStart)} a {formatDayLong(item.periodEnd)}
                      </p>
                      <p className="text-sub text-ink-2">
                        {account?.nickname ?? "Conta"} · {item.lineCount} {item.lineCount === 1 ? "lançamento" : "lançamentos"} ({item.newLineCount} {item.newLineCount === 1 ? "novo" : "novos"})
                      </p>
                    </div>
                    <Button variant="chip" size="md" aria-expanded={isOpen} aria-label={`${isOpen ? "Fechar" : "Ver"} a comparação do extrato de ${formatDayLong(item.periodStart)}`} onClick={() => setOpenId(isOpen ? null : item.id)} className="rounded-full!">
                      {isOpen ? "Fechar" : "Ver comparação"}
                    </Button>
                  </div>
                  {isOpen && <Comparison schoolId={schoolId} importId={item.id} />}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function AccountsCard({ schoolId, accounts, onChanged }: { schoolId: string; accounts: BankAccount[]; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [nickname, setNickname] = useState("");
  const [bankName, setBankName] = useState("");
  const [last4, setLast4] = useState("");
  const [purpose, setPurpose] = useState<AccountPurpose>("GENERAL");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (busy) return;
    const problems: Record<string, string> = {};
    if (!nickname.trim()) problems.nickname = "Dê um apelido à conta (ex.: Conta principal).";
    if (!bankName.trim()) problems.bank_name = "Escreva o nome do banco.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    setGeneral(null);
    const result = await api.reconciliation.createAccount(schoolId, { nickname: nickname.trim(), bankName: bankName.trim(), accountLast4: last4 || null, purpose });
    setBusy(false);
    if (!result.ok) return setGeneral(describeError(result.error, "Não foi possível salvar a conta."));
    setOpen(false);
    setNickname("");
    setBankName("");
    setLast4("");
    setPurpose("GENERAL");
    onChanged();
  }

  return (
    <Card title="Contas bancárias" action={<Button variant="secondary" size="md" onClick={() => setOpen(true)} className="rounded-full!">Nova conta</Button>}>
      {accounts.length === 0 ? (
        <p className="text-body text-ink-2">Cadastre a conta onde a escola recebe. Guardamos só o apelido, o banco e os últimos dígitos.</p>
      ) : (
        <ul aria-label="Contas bancárias" className="divide-y divide-line">
          {accounts.map((account) => (
            <li key={account.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
              <div className="min-w-0 flex-1 basis-48">
                <p className="font-semibold text-brand-800">{account.nickname}</p>
                <p className="text-sub text-ink-2">
                  {account.bankName}
                  {account.accountLast4 ? ` · final ${account.accountLast4}` : ""} · {account.purpose === "PDDE" ? "PDDE (verba do governo)" : "Fundo geral"}
                </p>
              </div>
              <StatusPill tone={account.isActive ? "success" : "neutral"}>{account.isActive ? "Ativa" : "Desligada"}</StatusPill>
              <Button variant="plain" size="md" onClick={() => void api.reconciliation.setAccountActive(schoolId, account.id, !account.isActive).then(onChanged)} aria-label={`${account.isActive ? "Desligar" : "Ligar"} a conta ${account.nickname}`} className="rounded-full!">
                {account.isActive ? "Desligar" : "Ligar"}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <FormModal open={open} title="Nova conta bancária" intro="Só o apelido, o banco e os últimos dígitos. O número completo da conta não é guardado." onClose={() => setOpen(false)} busy={busy}>
        <form method="post" noValidate aria-label="Nova conta bancária" onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-5">
          <TextField label="Apelido" name="account-nickname" autoComplete="off" maxLength={60} value={nickname} onChange={(e) => setNickname(e.target.value)} error={errors.nickname} />
          <TextField label="Banco" name="account-bank" autoComplete="off" maxLength={60} value={bankName} onChange={(e) => setBankName(e.target.value)} error={errors.bank_name} />
          <TextField label="Últimos dígitos da conta" optional name="account-last4" inputMode="numeric" autoComplete="off" maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value.replace(/\D/g, "").slice(0, 4))} />
          <fieldset>
            <legend className="mb-2 text-sub font-semibold text-ink">Para que serve</legend>
            <div className="flex flex-wrap gap-2.5">
              {(["GENERAL", "PDDE"] as const).map((p) => (
                <button key={p} type="button" aria-pressed={purpose === p} onClick={() => setPurpose(p)} className={chipClass(purpose === p)}>
                  {p === "GENERAL" ? "Fundo geral" : "PDDE (verba do governo)"}
                </button>
              ))}
            </div>
          </fieldset>
          <div aria-live="polite">{general && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{general}</p>}</div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Salvar conta" pendingLabel="Salvando…" pending={busy} />
        </form>
      </FormModal>
    </Card>
  );
}

function ImportCard({ schoolId, accounts, onImported }: { schoolId: string; accounts: BankAccount[]; onImported: (item: StatementImport) => void }) {
  const [accountId, setAccountId] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const chosen = accountId || accounts[0]?.id || "";

  async function send(file: File) {
    if (busy || !chosen) return;
    setBusy(true);
    setProblem(null);
    setNotice(null);
    const result = await api.reconciliation.import(schoolId, chosen, file);
    setBusy(false);
    if (input.current) input.current.value = "";
    if (!result.ok) return setProblem(describeError(result.error, "Não foi possível enviar o extrato."));
    setNotice(`Extrato enviado: ${result.data.newLineCount} ${result.data.newLineCount === 1 ? "lançamento novo" : "lançamentos novos"}.`);
    onImported(result.data);
  }

  return (
    <Card title="Enviar extrato (OFX)">
      {accounts.length === 0 ? (
        <p className="text-body text-ink-2">Cadastre uma conta bancária ativa para poder enviar um extrato.</p>
      ) : (
        <div className="space-y-4">
          <p className="max-w-[62ch] text-sub text-ink-2">No site ou app do seu banco, exporte o extrato no formato <strong className="font-semibold text-ink">OFX</strong> e envie aqui. O arquivo não fica guardado: só os lançamentos, sem CPF nem CNPJ.</p>
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-0 basis-60">
              <label htmlFor="import-account" className="mb-2 block text-sub font-semibold text-ink">Conta</label>
              <select id="import-account" value={chosen} onChange={(e) => setAccountId(e.target.value)} className="block min-h-[3.375rem] w-full rounded-ctl border-[1.5px] border-field-border bg-white px-4 text-[1rem] text-ink">
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.nickname}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="import-file" className="sr-only">Arquivo OFX do extrato</label>
              <input id="import-file" ref={input} type="file" accept=".ofx,application/x-ofx,text/plain" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void send(file); }} className="block min-h-11 max-w-full text-sub file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-full file:border file:border-line-strong file:bg-white file:px-5 file:text-sub file:font-semibold file:text-brand-800" />
            </div>
          </div>
          <div aria-live="polite" aria-busy={busy}>
            {busy && <p className="text-sub text-ink-2">Lendo o extrato…</p>}
            {notice && !problem && <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
            {problem && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{problem}</p>}
          </div>
        </div>
      )}
    </Card>
  );
}

type Tab = "matched" | "missingInSystem" | "missingInBank" | "divergences";

function Comparison({ schoolId, importId }: { schoolId: string; importId: string }) {
  const [tab, setTab] = useState<Tab>("matched");
  const [loaded, setLoaded] = useState<{ id: string; res: ApiResult<Reconciliation> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.reconciliation.compare(schoolId, importId).then((res) => {
      if (!cancelled) setLoaded({ id: importId, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, importId]);

  if (loaded?.id !== importId) return <p role="status" className="border-t border-line px-4 py-4 text-sub text-ink-2">Comparando com o caixa…</p>;
  if (!loaded.res.ok) return <p role="alert" className="border-t border-line px-4 py-4 text-sub font-medium text-bad">{describeError(loaded.res.error, "Não foi possível comparar.")}</p>;
  const r = loaded.res.data;
  const tabs: Array<{ id: Tab; label: string; count: number }> = [
    { id: "matched", label: "Conferidos", count: r.matched.length },
    { id: "missingInSystem", label: "Faltam no sistema", count: r.missingInSystem.length },
    { id: "missingInBank", label: "Faltam no extrato", count: r.missingInBank.length },
    { id: "divergences", label: "Divergências", count: r.divergences.length },
  ];
  return (
    <div className="space-y-4 border-t border-line px-4 py-4">
      <div role="group" aria-label="Partes da comparação" className="flex flex-wrap gap-2.5">
        {tabs.map((t) => (
          <button key={t.id} type="button" aria-pressed={tab === t.id} onClick={() => setTab(t.id)} className={chipClass(tab === t.id)}>
            {t.label} ({t.count})
          </button>
        ))}
      </div>
      {tab === "matched" && <Rows empty="Nenhum lançamento do extrato foi conferido com o caixa ainda." items={r.matched.map((m) => ({ key: m.line.lineId, line: m.line, entry: m.entry }))} />}
      {tab === "missingInSystem" && <Rows hint="No extrato do banco, mas não no caixa do sistema." empty="Tudo o que está no extrato já está no caixa." items={r.missingInSystem.map((line) => ({ key: line.lineId, line }))} />}
      {tab === "missingInBank" && <Rows hint="No caixa do sistema, mas não apareceu neste extrato." empty="Tudo o que está no caixa apareceu no extrato." items={r.missingInBank.map((entry) => ({ key: entry.transactionId, entry }))} />}
      {tab === "divergences" && (
        <div className="space-y-3">
          <p className="text-sub text-ink-2">O sistema não adivinha: quando há dúvida, ele deixa para uma pessoa decidir.</p>
          {r.divergences.length === 0 && <p className="text-body text-ink-2">Nenhuma divergência.</p>}
          {r.divergences.map((d) => (
            <div key={d.line.lineId} className="rounded-[var(--r-md)] border border-line p-3">
              <p className="mb-2 text-foot font-semibold text-warn">{d.reason === "amount_differs" ? "O identificador do Pix bate, mas o valor é outro." : "Mais de um lançamento poderia ser este."}</p>
              <Rows empty="" items={[{ key: d.line.lineId, line: d.line }, ...d.candidates.map((entry) => ({ key: entry.transactionId, entry }))]} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Rows({ items, empty, hint }: { items: Array<{ key: string; line?: BankLine; entry?: LedgerEntry }>; empty: string; hint?: string }) {
  if (items.length === 0) return <p className="text-body text-ink-2">{empty}</p>;
  return (
    <div className="space-y-2">
      {hint && <p className="text-sub text-ink-2">{hint}</p>}
      <ul className="divide-y divide-line">
        {items.map((item) => (
          <li key={item.key} className="flex flex-wrap items-start gap-x-4 gap-y-1 py-2.5">
            <div className="min-w-0 flex-1 basis-60">
              {item.line && (
                <p className="text-sub text-ink [overflow-wrap:anywhere]">
                  <span className="font-semibold">Banco · {formatDayLong(item.line.postedOn)}</span> · {item.line.memo || "sem descrição"}
                  {item.line.looksLikeFee && <span className="ml-2"><StatusPill tone="warning">parece tarifa</StatusPill></span>}
                </p>
              )}
              {item.entry && (
                <p className="text-sub text-ink [overflow-wrap:anywhere]">
                  <span className="font-semibold">Caixa · {formatDayLong(item.entry.day)}</span> · {KIND_LABELS[item.entry.kind] ?? item.entry.kind} nº {item.entry.referenceCode}
                  {item.entry.netCents !== null && ` · o banco recebe ${formatBRL(item.entry.netCents)} (a tarifa do gateway já saiu)`}
                </p>
              )}
            </div>
            <p className="shrink-0 text-body font-bold tabular-nums text-brand-800">{formatBRL(item.line?.amountCents ?? item.entry?.amountCents ?? 0)}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
