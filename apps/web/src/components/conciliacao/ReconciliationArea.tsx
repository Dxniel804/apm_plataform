"use client";

import { useEffect, useRef, useState } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { StatusPill } from "@/components/ui/StatusPill";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { AccountPurpose, ApiError, ApiResult, BankAccount, BankLine, CsvProfile, LedgerEntry, LineActionInput, Reconciliation, StatementImport, StatementPreview } from "@/lib/api/types";
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
    case "not_a_csv_file":
      return "Não conseguimos ler este arquivo como planilha CSV. Exporte o extrato de novo.";
    case "not_a_pdf_file":
      return "Este PDF não pôde ser aberto. Baixe o extrato de novo no site do banco.";
    case "pdf_without_text":
      return "Este PDF é uma imagem (escaneado) e não dá para ler. Peça ao banco o extrato em OFX ou CSV.";
    case "pdf_encrypted":
      return "Este PDF tem senha. Baixe uma versão sem senha ou use OFX ou CSV.";
    case "pdf_too_many_pages":
      return "O PDF tem páginas demais. Escolha um período menor.";
    case "pdf_year_unknown":
      return "Não achamos o ano no PDF. Use OFX ou CSV, ou baixe o extrato com as datas completas.";
    case "csv_profile_invalid":
      return "O mapa de colunas não está certo. Confira as colunas e tente de novo.";
    case "review_required":
      return "Esta linha veio de um PDF. Marque que você conferiu a linha com o extrato original.";
    case "already_imported":
      return "Este arquivo já foi enviado antes.";
    case "account_inactive":
      return "Esta conta está desligada. Escolha outra.";
    case "permission_denied":
      return "Você não tem permissão para mexer na conciliação.";
    case "conflict":
      return "Já existe uma conta com esse apelido.";
    case "already_resolved":
      return "Esta linha já foi resolvida por alguém. Atualize a lista.";
    case "validation_error":
      return "Confira os dados: o motivo precisa ter de 3 a 200 letras, e o Pix direto precisa do identificador do banco.";
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
 * listas. A comparacao so le. O que esta no banco e nao no caixa a gestao RESOLVE linha a linha (registrar a entrada ou a
 * tarifa, ou ignorar com motivo), sempre confirmando. Quem decide o pareamento e a API (certeza ou divergencia).
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
        Compare o extrato do banco com o caixa do sistema. A comparação só <strong className="font-semibold text-ink">confere</strong>: nada é lançado sozinho. O que estiver no banco e faltar no sistema, você resolve linha a linha, confirmando.
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
  const [mapping, setMapping] = useState<{ file: File; preview: StatementPreview } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const chosen = accountId || accounts[0]?.id || "";
  const account = accounts.find((a) => a.id === chosen);

  async function finish(file: File, profile: CsvProfile | null) {
    const result = await api.reconciliation.import(schoolId, chosen, file, profile);
    setBusy(false);
    if (input.current) input.current.value = "";
    if (!result.ok) {
      if (result.error.code === "csv_needs_mapping") return setProblem("Não conseguimos achar as colunas deste CSV. Envie de novo e escolha as colunas.");
      return setProblem(describeError(result.error, "Não foi possível enviar o extrato."));
    }
    setMapping(null);
    const review = result.data.source === "PDF" ? " As linhas de PDF precisam ser conferidas uma a uma antes de virar lançamento." : "";
    setNotice(`Extrato enviado: ${result.data.newLineCount} ${result.data.newLineCount === 1 ? "lançamento novo" : "lançamentos novos"}.${review}`);
    onImported(result.data);
  }

  async function send(file: File) {
    if (busy || !chosen) return;
    setBusy(true);
    setProblem(null);
    setNotice(null);
    // Um CSV de uma conta que ainda nao tem o mapa de colunas passa antes pela confirmacao das colunas.
    if (/\.csv$/i.test(file.name) && !account?.csvProfile) {
      const preview = await api.reconciliation.preview(schoolId, chosen, file);
      if (!preview.ok) {
        setBusy(false);
        if (input.current) input.current.value = "";
        return setProblem(describeError(preview.error, "Não foi possível ler o arquivo."));
      }
      if (preview.data.kind === "CSV") {
        setBusy(false);
        return setMapping({ file, preview: preview.data });
      }
    }
    await finish(file, null);
  }

  return (
    <Card title="Enviar extrato (OFX, CSV ou PDF)">
      {accounts.length === 0 ? (
        <p className="text-body text-ink-2">Cadastre uma conta bancária ativa para poder enviar um extrato.</p>
      ) : (
        <div className="space-y-4">
          <p className="max-w-[62ch] text-sub text-ink-2">
            No site ou app do seu banco, exporte o extrato. O melhor é <strong className="font-semibold text-ink">OFX</strong>; também lemos <strong className="font-semibold text-ink">CSV</strong> (planilha) e <strong className="font-semibold text-ink">PDF</strong> com texto. O arquivo não fica guardado: só os lançamentos, sem CPF nem CNPJ. Linhas vindas de PDF precisam ser conferidas por você.
          </p>
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
              <label htmlFor="import-file" className="sr-only">Arquivo do extrato (OFX, CSV ou PDF)</label>
              <input id="import-file" ref={input} type="file" accept=".ofx,.csv,.pdf,application/x-ofx,application/pdf,text/csv,text/plain" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void send(file); }} className="block min-h-11 max-w-full text-sub file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-full file:border file:border-line-strong file:bg-white file:px-5 file:text-sub file:font-semibold file:text-brand-800" />
            </div>
          </div>
          <div aria-live="polite" aria-busy={busy}>
            {busy && <p className="text-sub text-ink-2">Lendo o extrato…</p>}
            {notice && !problem && <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
            {problem && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{problem}</p>}
          </div>
        </div>
      )}
      {mapping && (
        <CsvMapping
          preview={mapping.preview}
          busy={busy}
          onCancel={() => {
            setMapping(null);
            if (input.current) input.current.value = "";
          }}
          onConfirm={(profile) => {
            setBusy(true);
            void finish(mapping.file, profile);
          }}
        />
      )}
    </Card>
  );
}

const DEFAULT_PROFILE: CsvProfile = { delimiter: ";", has_header: true, date_col: 0, date_order: "DMY", memo_col: 1, decimal: ",", amount_col: 2, debit_positive: false, credit_col: null, debit_col: null, id_col: null };

/** A pessoa confere (ou escolhe) quais colunas do CSV sao a data, o texto e o valor. Guardado na conta para as proximas vezes. */
function CsvMapping({ preview, busy, onCancel, onConfirm }: { preview: StatementPreview; busy: boolean; onCancel: () => void; onConfirm: (profile: CsvProfile) => void }) {
  const [profile, setProfile] = useState<CsvProfile>(preview.suggestedProfile ?? DEFAULT_PROFILE);
  const [split, setSplit] = useState(profile.credit_col !== null);
  const width = Math.max(1, ...preview.sample.map((r) => r.length), preview.header?.length ?? 0);
  const names = Array.from({ length: width }, (_, i) => preview.header?.[i]?.trim() || `Coluna ${i + 1}`);
  const select = (id: string, label: string, value: number | null, set: (n: number | null) => void, optional = false) => (
    <div>
      <label htmlFor={id} className="mb-2 block text-sub font-semibold text-ink">{label}</label>
      <select id={id} value={value ?? ""} onChange={(e) => set(e.target.value === "" ? null : Number(e.target.value))} className="block min-h-[3.375rem] w-full rounded-ctl border-[1.5px] border-field-border bg-white px-4 text-[1rem] text-ink">
        {optional && <option value="">Nenhuma</option>}
        {names.map((n, i) => (
          <option key={i} value={i}>{n}</option>
        ))}
      </select>
    </div>
  );
  const valid = split ? profile.credit_col !== null && profile.debit_col !== null : profile.amount_col !== null;
  return (
    <FormModal
      open
      title="Confirme as colunas do CSV"
      intro={preview.suggestedProfile ? "Achamos as colunas abaixo. Confira com as primeiras linhas do arquivo. Guardamos para os próximos envios desta conta." : "Não conseguimos achar as colunas sozinhos. Diga qual é a data, o texto e o valor."}
      onClose={onCancel}
      busy={busy}
    >
      <form method="post" noValidate aria-label="Colunas do CSV" onSubmit={(e) => { e.preventDefault(); if (valid) onConfirm({ ...profile, amount_col: split ? null : profile.amount_col, credit_col: split ? profile.credit_col : null, debit_col: split ? profile.debit_col : null }); }} className="space-y-5">
        <div className="max-h-44 overflow-auto rounded-[var(--r-md)] border border-line">
          <table className="w-full text-foot">
            <tbody>
              {preview.sample.map((row, r) => (
                <tr key={r} className={r === 0 && preview.header ? "bg-bg font-semibold" : ""}>
                  {names.map((_, c) => (
                    <td key={c} className="whitespace-nowrap px-2 py-1">{row[c] ?? ""}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {select("csv-date", "Coluna da data", profile.date_col, (n) => setProfile({ ...profile, date_col: n ?? 0 }))}
          {select("csv-memo", "Coluna do texto", profile.memo_col, (n) => setProfile({ ...profile, memo_col: n ?? 0 }))}
        </div>
        <fieldset>
          <legend className="mb-2 text-sub font-semibold text-ink">Como o valor aparece</legend>
          <div className="flex flex-wrap gap-2.5">
            <button type="button" aria-pressed={!split} onClick={() => setSplit(false)} className={chipClass(!split)}>Uma coluna de valor</button>
            <button type="button" aria-pressed={split} onClick={() => setSplit(true)} className={chipClass(split)}>Crédito e débito separados</button>
          </div>
        </fieldset>
        {!split ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {select("csv-amount", "Coluna do valor", profile.amount_col, (n) => setProfile({ ...profile, amount_col: n }))}
            <label className="flex min-h-11 items-center gap-3 self-end text-sub text-ink">
              <input type="checkbox" checked={profile.debit_positive} onChange={(e) => setProfile({ ...profile, debit_positive: e.target.checked })} className="size-5" />
              Saídas aparecem como número positivo
            </label>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {select("csv-credit", "Coluna de crédito (entrada)", profile.credit_col, (n) => setProfile({ ...profile, credit_col: n }))}
            {select("csv-debit", "Coluna de débito (saída)", profile.debit_col, (n) => setProfile({ ...profile, debit_col: n }))}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="csv-order" className="mb-2 block text-sub font-semibold text-ink">Formato da data</label>
            <select id="csv-order" value={profile.date_order} onChange={(e) => setProfile({ ...profile, date_order: e.target.value as "DMY" | "YMD" })} className="block min-h-[3.375rem] w-full rounded-ctl border-[1.5px] border-field-border bg-white px-4 text-[1rem] text-ink">
              <option value="DMY">31/12/2026 (dia/mês/ano)</option>
              <option value="YMD">2026-12-31 (ano-mês-dia)</option>
            </select>
          </div>
          <div>
            <label htmlFor="csv-decimal" className="mb-2 block text-sub font-semibold text-ink">Separador dos centavos</label>
            <select id="csv-decimal" value={profile.decimal} onChange={(e) => setProfile({ ...profile, decimal: e.target.value as "," | "." })} className="block min-h-[3.375rem] w-full rounded-ctl border-[1.5px] border-field-border bg-white px-4 text-[1rem] text-ink">
              <option value=",">Vírgula (1.234,56)</option>
              <option value=".">Ponto (1234.56)</option>
            </select>
          </div>
        </div>
        <label className="flex min-h-11 items-center gap-3 text-sub text-ink">
          <input type="checkbox" checked={profile.has_header} onChange={(e) => setProfile({ ...profile, has_header: e.target.checked })} className="size-5" />
          A primeira linha é o título das colunas
        </label>
        <FormButtons onCancel={onCancel} cancelLabel="Cancelar" submitLabel="Usar estas colunas e enviar" pendingLabel="Enviando…" pending={busy} />
      </form>
    </FormModal>
  );
}

type Tab = "matched" | "missingInSystem" | "missingInBank" | "divergences";

function Comparison({ schoolId, importId }: { schoolId: string; importId: string }) {
  const [tab, setTab] = useState<Tab>("matched");
  const [version, setVersion] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const key = `${importId}|${version}`;
  const [loaded, setLoaded] = useState<{ id: string; res: ApiResult<Reconciliation> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.reconciliation.compare(schoolId, importId).then((res) => {
      if (!cancelled) setLoaded({ id: key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, importId, key]);

  if (loaded?.id !== key && !loaded) return <p role="status" className="border-t border-line px-4 py-4 text-sub text-ink-2">Comparando com o caixa…</p>;
  if (!loaded) return null;
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
      {done && <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{done}</p>}
      <div role="group" aria-label="Partes da comparação" className="flex flex-wrap gap-2.5">
        {tabs.map((t) => (
          <button key={t.id} type="button" aria-pressed={tab === t.id} onClick={() => setTab(t.id)} className={chipClass(tab === t.id)}>
            {t.label} ({t.count})
          </button>
        ))}
      </div>
      {tab === "matched" && <Rows empty="Nenhum lançamento do extrato foi conferido com o caixa ainda." items={r.matched.map((m) => ({ key: m.line.lineId, line: m.line, entry: m.entry }))} />}
      {tab === "missingInSystem" && (
        <div className="space-y-4">
          <Rows
            hint="O banco mostra, mas o caixa do sistema não tem. Para cada linha, escolha: registrar no caixa (uma entrada ou uma tarifa) ou ignorar, explicando o motivo."
            empty="Tudo o que está no extrato já está no caixa."
            items={r.missingInSystem.map((line) => ({
              key: line.lineId,
              line,
              actions: (
                <LineActions
                  schoolId={schoolId}
                  line={line}
                  onDone={(message) => {
                    setDone(message);
                    setVersion((n) => n + 1);
                  }}
                />
              ),
            }))}
          />
          {r.ignored.length > 0 && (
            <div>
              <h3 className="mb-1 text-sub font-semibold text-ink">Ignorados ({r.ignored.length})</h3>
              <ul aria-label="Linhas ignoradas" className="divide-y divide-line">
                {r.ignored.map((i) => (
                  <li key={i.line.lineId} className="flex flex-wrap items-start justify-between gap-x-4 py-2 text-sub text-ink-2">
                    <span className="min-w-0 flex-1 basis-60 [overflow-wrap:anywhere]">
                      {formatDayLong(i.line.postedOn)} · {i.line.memo || "sem descrição"} · <em>Motivo: {i.reason}</em>
                    </span>
                    <span className="tabular-nums">{formatBRL(i.line.amountCents)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {tab === "missingInBank" && (
        <Rows
          hint="O caixa do sistema tem, mas não apareceu neste extrato. O extrato do banco não se altera. Em geral é um Pix ou depósito que ainda não compensou (envie um extrato mais novo depois), ou um lançamento feito com valor ou data errados (corrija em Despesas ou Contribuições)."
          empty="Tudo o que está no caixa apareceu no extrato."
          items={r.missingInBank.map((entry) => ({ key: entry.transactionId, entry }))}
        />
      )}
      {tab === "divergences" && (
        <div className="space-y-3">
          <p className="text-sub text-ink-2">O sistema não adivinha: quando há dúvida, ele deixa para uma pessoa decidir. Confira com o comprovante e corrija o lançamento do sistema (o extrato do banco não muda).</p>
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

function Rows({ items, empty, hint }: { items: Array<{ key: string; line?: BankLine; entry?: LedgerEntry; actions?: React.ReactNode }>; empty: string; hint?: string }) {
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
                  {item.line.needsReview && <span className="ml-2"><StatusPill tone="warning">veio de PDF: confira</StatusPill></span>}
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
            {item.actions && <div className="flex w-full flex-wrap gap-2">{item.actions}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const INCOME_CATEGORIES = [
  { key: "parent_contribution", label: "Contribuição de pais" },
  { key: "donation", label: "Doação" },
  { key: "other_income", label: "Outra entrada" },
] as const;

/** Os botoes de uma linha que esta no banco e nao no caixa. Nada e feito sem a confirmacao da pessoa. */
function LineActions({ schoolId, line, onDone }: { schoolId: string; line: BankLine; onDone: (message: string) => void }) {
  const income = line.amountCents > 0;
  const [mode, setMode] = useState<"income" | "fee" | "ignore" | null>(null);
  const [method, setMethod] = useState<"PIX_DIRECT" | "TRANSFER">(line.endToEndId ? "PIX_DIRECT" : "TRANSFER");
  const [category, setCategory] = useState<(typeof INCOME_CATEGORIES)[number]["key"]>("parent_contribution");
  const [who, setWho] = useState("");
  const [reason, setReason] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  function close() {
    setMode(null);
    setProblem(null);
  }

  async function confirm() {
    if (busy || !mode) return;
    if (mode === "ignore" && reason.trim().length < 3) return setProblem("Explique o motivo (pelo menos 3 letras).");
    if (mode !== "ignore" && line.needsReview && !reviewed) return setProblem("Marque que você conferiu esta linha com o extrato original.");
    setBusy(true);
    setProblem(null);
    const input: LineActionInput =
      mode === "income"
        ? { action: "REGISTER_INCOME", method, categoryKey: category, ...(who.trim() ? { guardianName: who.trim() } : {}), ...(reviewed ? { reviewed: true } : {}) }
        : mode === "fee"
          ? { action: "REGISTER_FEE", ...(reviewed ? { reviewed: true } : {}) }
          : { action: "IGNORE", reason: reason.trim() };
    const result = await api.reconciliation.actOnLine(schoolId, line.lineId, input);
    setBusy(false);
    if (!result.ok) return setProblem(describeError(result.error, "Não foi possível concluir. Nada foi alterado."));
    close();
    onDone(
      result.data.action === "IGNORED"
        ? "Linha ignorada. O motivo ficou guardado."
        : `Registrado no caixa${result.data.referenceCode ? ` (${result.data.referenceCode})` : ""}. A linha agora está em Conferidos.`,
    );
  }

  const title = mode === "income" ? "Registrar entrada no caixa" : mode === "fee" ? "Registrar tarifa bancária" : "Ignorar esta linha";
  return (
    <>
      {income && (
        <Button variant="chip" size="md" onClick={() => setMode("income")} aria-label={`Registrar a entrada de ${formatBRL(line.amountCents)} de ${formatDayLong(line.postedOn)}`} className="rounded-full!">
          Registrar entrada
        </Button>
      )}
      {!income && line.looksLikeFee && (
        <Button variant="chip" size="md" onClick={() => setMode("fee")} aria-label={`Registrar a tarifa de ${formatBRL(-line.amountCents)} de ${formatDayLong(line.postedOn)}`} className="rounded-full!">
          Registrar tarifa
        </Button>
      )}
      <Button variant="plain" size="md" onClick={() => setMode("ignore")} aria-label={`Ignorar a linha de ${formatBRL(line.amountCents)} de ${formatDayLong(line.postedOn)}`} className="rounded-full!">
        Ignorar
      </Button>
      <FormModal
        open={mode !== null}
        title={title}
        intro={
          mode === "ignore"
            ? "A linha some da lista de pendências e o motivo fica guardado com o seu nome."
            : `Vai entrar no caixa ${formatBRL(Math.abs(line.amountCents))}, no dia ${formatDayLong(line.postedOn)}, com o seu nome como quem registrou. Isso não pode ser desfeito por aqui.`
        }
        onClose={close}
        busy={busy}
      >
        <form method="post" noValidate aria-label={title} onSubmit={(e) => { e.preventDefault(); void confirm(); }} className="space-y-5">
          <p className="rounded-[var(--r-md)] bg-bg px-4 py-3 text-sub text-ink [overflow-wrap:anywhere]">
            {formatDayLong(line.postedOn)} · {line.memo || "sem descrição"} · <strong>{formatBRL(line.amountCents)}</strong>
          </p>
          {mode === "income" && (
            <>
              <fieldset>
                <legend className="mb-2 text-sub font-semibold text-ink">Como o dinheiro chegou</legend>
                <div className="flex flex-wrap gap-2.5">
                  {line.endToEndId && (
                    <button type="button" aria-pressed={method === "PIX_DIRECT"} onClick={() => setMethod("PIX_DIRECT")} className={chipClass(method === "PIX_DIRECT")}>Pix direto na conta</button>
                  )}
                  <button type="button" aria-pressed={method === "TRANSFER"} onClick={() => setMethod("TRANSFER")} className={chipClass(method === "TRANSFER")}>Transferência ou depósito</button>
                </div>
              </fieldset>
              <div>
                <label htmlFor="line-category" className="mb-2 block text-sub font-semibold text-ink">Tipo de entrada</label>
                <select id="line-category" value={category} onChange={(e) => setCategory(e.target.value as typeof category)} className="block min-h-[3.375rem] w-full rounded-ctl border-[1.5px] border-field-border bg-white px-4 text-[1rem] text-ink">
                  {INCOME_CATEGORIES.map((c) => (
                    <option key={c.key} value={c.key}>{c.label}</option>
                  ))}
                </select>
              </div>
              <TextField label="Quem enviou" optional name="line-who" autoComplete="off" maxLength={120} value={who} onChange={(e) => setWho(e.target.value)} />
            </>
          )}
          {mode !== "ignore" && line.needsReview && (
            <label className="flex items-start gap-3 rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-ink">
              <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} className="mt-0.5 size-5 shrink-0" />
              Esta linha foi lida de um PDF. Conferi a data, o valor e o texto com o extrato original.
            </label>
          )}
          {mode === "ignore" && <TextField label="Motivo" name="line-reason" autoComplete="off" maxLength={200} hint="Obrigatório. Ex.: pago pela prefeitura, não é da APM." value={reason} onChange={(e) => setReason(e.target.value)} />}
          <div aria-live="polite">{problem && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{problem}</p>}</div>
          <FormButtons onCancel={close} cancelLabel="Voltar" submitLabel={mode === "ignore" ? "Ignorar a linha" : "Confirmar e registrar"} pendingLabel="Salvando…" pending={busy} />
        </form>
      </FormModal>
    </>
  );
}
