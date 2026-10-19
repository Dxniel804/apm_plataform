"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { StatusPill } from "@/components/ui/StatusPill";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiError, ApiResult } from "@/lib/api/types";
import {
  pddeReportHref,
  type PddeAlert,
  type PddeDocKind,
  type PddeEconomic,
  type PddeKind,
  type PddeLine,
  type PddeMonth,
  type PddeProgram,
  type PddeYear,
} from "@/lib/api/pdde";
import { formatDayLong } from "@/lib/format";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { currentLocalPeriod, periodLabel, recentPeriods } from "@/lib/statement-labels";

const PROGRAM_LABELS: Record<PddeProgram, string> = {
  BASICO: "PDDE Básico",
  EQUIDADE: "PDDE Equidade",
  QUALIDADE: "PDDE Qualidade",
  CONECTADO: "Educação Conectada",
  OUTRO: "Outro programa",
};
const KIND_LABELS: Record<PddeKind, string> = {
  TRANSFER: "Repasse (dinheiro que entrou)",
  EXPENSE: "Despesa",
  TAX_TO_EEX: "Imposto pago direto à prefeitura",
  REFUND: "Estorno ou devolução",
  INELIGIBLE: "Despesa não elegível",
};
const DOC_LABELS: Record<PddeDocKind, string> = { NFE: "Nota fiscal eletrônica (NF-e)", INVOICE: "Fatura", RECEIPT: "Recibo", OTHER: "Outro documento" };
const ECONOMIC_LABELS: Record<PddeEconomic, string> = { CUSTEIO: "Custeio", CAPITAL: "Capital" };
const STATUS: Record<PddeLine["status"], { tone: "warning" | "info" | "success"; label: string }> = {
  PENDING: { tone: "warning", label: "Pendente" },
  PARTIAL: { tone: "info", label: "Parcial" },
  DONE: { tone: "success", label: "Concluída" },
};

const programName = (program: PddeProgram | null, label: string | null) => (program === null ? "" : program === "OUTRO" ? (label ?? PROGRAM_LABELS.OUTRO) : PROGRAM_LABELS[program]);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function describe(error: ApiError): string {
  if (error.kind === "network" || error.kind === "timeout") return "Não foi possível falar com o servidor. Nada foi alterado.";
  switch (error.code) {
    case "document_key_used":
      return "Esta nota fiscal já comprova outra linha.";
    case "line_is_not_an_expense":
      return "Documento só se registra em uma saída da conta.";
    case "rule_violation":
      return "Não foi possível salvar: confira se o tipo combina com a linha (repasse é entrada, despesa é saída) e se os documentos não somam mais que a linha.";
    case "validation_error":
      return "Confira os dados. Despesa precisa de programa, custeio ou capital e objeto; a chave da NF-e tem 44 números.";
    case "permission_denied":
      return "Você não tem permissão para mexer no PDDE.";
    default:
      return error.status === 404 ? "Esta linha não está mais aqui. Atualize a página." : "Não foi possível concluir. Tente de novo.";
  }
}

function alertText(a: PddeAlert): string {
  const where = a.program ? programName(a.program, null) : "";
  switch (a.code) {
    case "fee_on_pdde_account":
      return `${plural(a.count, "tarifa bancária", "tarifas bancárias")} na conta do PDDE (${formatBRL(a.cents)}). A conta do PDDE é isenta de tarifas e o dinheiro não pode pagá-las: peça ao banco o estorno.`;
    case "pending_lines":
      return `${plural(a.count, "lançamento", "lançamentos")} sem classificação ou sem documento.`;
    case "spent_over_received":
      return `${where}: gastou ${formatBRL(a.cents)} a mais em ${a.economicCategory === "CAPITAL" ? "capital" : "custeio"} do que recebeu nessa categoria. Usar custeio em capital, ou o contrário, faz a prestação ser aprovada só com ressalva.`;
    case "year_end_reconciliation":
      return `Falta o extrato de dezembro (até 31/12) em ${plural(a.count, "conta", "contas")}: a prestação pede a conciliação bancária do saldo de 31/12.`;
    case "deadline":
      return `A prefeitura recebe a prestação até ${a.date ? formatDayLong(a.date) : "30/04"} e ainda há ${plural(a.count, "pendência", "pendências")}. Confirme com ela o prazo da sua escola.`;
    case "deadline_passed":
      return `O prazo de ${a.date ? formatDayLong(a.date) : "30/04"} já passou e ainda há ${plural(a.count, "pendência", "pendências")}. Procure a prefeitura.`;
  }
}

function Alerts({ alerts }: { alerts: PddeAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <ul aria-label="Atenção" className="mt-4 space-y-2">
      {alerts.map((a, i) => (
        <li key={`${a.code}-${i}`} className="rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
          {alertText(a)}
        </li>
      ))}
    </ul>
  );
}

function Money({ label, cents, onChange, hint }: { label: string; cents: number; onChange: (v: number) => void; hint?: string }) {
  return <TextField label={label} name={label} prefix="R$" inputMode="numeric" autoComplete="off" placeholder="0,00" hint={hint} value={cents === 0 ? "" : formatBRLNumber(cents)} onChange={(e) => onChange(centsFromDigits(e.target.value))} />;
}

// --- classify ------------------------------------------------------------------------------------

function ClassifyModal({ schoolId, line, onClose, onDone }: { schoolId: string; line: PddeLine; onClose: () => void; onDone: () => void }) {
  const credit = line.amountCents > 0;
  const current = line.classification;
  const [kind, setKind] = useState<PddeKind>(current?.kind ?? (credit ? "TRANSFER" : "EXPENSE"));
  const [program, setProgram] = useState<PddeProgram>(current?.program ?? "BASICO");
  const [label, setLabel] = useState(current?.programLabel ?? "");
  const [category, setCategory] = useState<PddeEconomic | "">(current?.economicCategory ?? "");
  const [object, setObject] = useState(current?.object ?? "");
  const [note, setNote] = useState(current?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsProgram = kind === "TRANSFER" || kind === "EXPENSE";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (kind === "EXPENSE" && (category === "" || object.trim() === "")) return setError("Despesa precisa de custeio ou capital e do objeto.");
    if (needsProgram && program === "OUTRO" && label.trim() === "") return setError("Diga o nome do programa.");
    setBusy(true);
    setError(null);
    const r = await api.pdde.classify(schoolId, line.lineId, {
      kind,
      ...(needsProgram ? { program, ...(program === "OUTRO" ? { programLabel: label.trim() } : {}) } : {}),
      ...(category !== "" && needsProgram ? { economicCategory: category } : {}),
      ...(kind === "EXPENSE" ? { object: object.trim() } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
    });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onDone();
  }

  const kinds: PddeKind[] = credit ? ["TRANSFER", "REFUND"] : ["EXPENSE", "TAX_TO_EEX", "INELIGIBLE", "REFUND"];
  return (
    <FormModal title="Classificar o lançamento" intro={`${formatDayLong(line.postedOn)} · ${formatBRL(line.amountCents)} · ${line.memo}`} onClose={onClose} busy={busy}>
      <form method="post" onSubmit={(e) => void submit(e)} className="space-y-5">
        <SelectField id="pdde-kind" label="O que é este lançamento" value={kind} onChange={(e) => setKind(e.target.value as PddeKind)}>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {KIND_LABELS[k]}
            </option>
          ))}
        </SelectField>
        {needsProgram && (
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField id="pdde-program" label="Programa" value={program} onChange={(e) => setProgram(e.target.value as PddeProgram)}>
              {(Object.keys(PROGRAM_LABELS) as PddeProgram[]).map((p) => (
                <option key={p} value={p}>
                  {PROGRAM_LABELS[p]}
                </option>
              ))}
            </SelectField>
            <SelectField id="pdde-category" label="Custeio ou capital" optional={kind === "TRANSFER"} value={category} onChange={(e) => setCategory(e.target.value as PddeEconomic | "")}>
              <option value="">{kind === "TRANSFER" ? "Não informar" : "Escolha"}</option>
              {(Object.keys(ECONOMIC_LABELS) as PddeEconomic[]).map((c) => (
                <option key={c} value={c}>
                  {ECONOMIC_LABELS[c]}
                </option>
              ))}
            </SelectField>
          </div>
        )}
        {needsProgram && program === "OUTRO" && <TextField label="Nome do programa" name="program-label" maxLength={60} value={label} onChange={(e) => setLabel(e.target.value)} />}
        {kind === "EXPENSE" && <TextField label="Objeto da despesa" name="object" maxLength={120} hint="Como a resolução do programa chama o gasto. Exemplo: material de consumo." value={object} onChange={(e) => setObject(e.target.value)} />}
        <TextField label="Observação" optional name="note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
        <FormButtons onCancel={onClose} submitLabel="Salvar" pending={busy} />
      </form>
    </FormModal>
  );
}

// --- documents -----------------------------------------------------------------------------------

function DocumentModal({ schoolId, line, onClose, onDone }: { schoolId: string; line: PddeLine; onClose: () => void; onDone: () => void }) {
  const left = -line.amountCents - line.documentedCents;
  const [docKind, setDocKind] = useState<PddeDocKind>("NFE");
  const [key, setKey] = useState("");
  const [number, setNumber] = useState("");
  const [issuedOn, setIssuedOn] = useState("");
  const [vendor, setVendor] = useState("");
  const [cents, setCents] = useState(left > 0 ? left : 0);
  const [stamped, setStamped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(issuedOn)) return setError("Informe a data do documento.");
    if (vendor.trim() === "" || cents <= 0) return setError("Informe o fornecedor e o valor.");
    setBusy(true);
    setError(null);
    const r = await api.pdde.addDocument(schoolId, line.lineId, {
      docKind,
      ...(docKind === "NFE" ? { accessKey: key } : {}),
      ...(number.trim() ? { docNumber: number.trim() } : {}),
      issuedOn,
      vendor: vendor.trim(),
      amountCents: cents,
      stamped,
    });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onDone();
  }

  return (
    <FormModal title="Registrar documento da despesa" intro={`${line.memo} · falta comprovar ${formatBRL(Math.max(left, 0))}`} onClose={onClose} busy={busy}>
      <form method="post" onSubmit={(e) => void submit(e)} className="space-y-5">
        <SelectField id="pdde-doc-kind" label="Tipo de documento" value={docKind} onChange={(e) => setDocKind(e.target.value as PddeDocKind)}>
          {(Object.keys(DOC_LABELS) as PddeDocKind[]).map((k) => (
            <option key={k} value={k}>
              {DOC_LABELS[k]}
            </option>
          ))}
        </SelectField>
        {docKind === "NFE" && <TextField label="Chave de acesso da NF-e" name="access-key" inputMode="numeric" autoComplete="off" hint="Os 44 números, com ou sem espaços." value={key} onChange={(e) => setKey(e.target.value)} />}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Número" optional name="number" maxLength={40} value={number} onChange={(e) => setNumber(e.target.value)} />
          <TextField label="Data do documento" name="issued-on" type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} />
        </div>
        <TextField label="Fornecedor" name="vendor" maxLength={120} value={vendor} onChange={(e) => setVendor(e.target.value)} />
        <Money label="Valor deste documento" cents={cents} onChange={setCents} hint="Pode ser menos que a linha: os documentos somam até o valor dela." />
        <label className="flex items-start gap-3 text-sub">
          <input type="checkbox" checked={stamped} onChange={(e) => setStamped(e.target.checked)} className="mt-1 size-5" />
          <span>O documento tem a expressão &quot;Pagos com recursos do&quot; e o nome do programa, e o atesto de recebimento assinado.</span>
        </label>
        <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
        <FormButtons onCancel={onClose} submitLabel="Registrar" pending={busy} />
      </form>
    </FormModal>
  );
}

// --- a line --------------------------------------------------------------------------------------

function LineItem({ schoolId, line, onChanged }: { schoolId: string; line: PddeLine; onChanged: () => void }) {
  const [classifying, setClassifying] = useState(false);
  const [documenting, setDocumenting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const c = line.classification;
  const isExpense = c?.kind === "EXPENSE";
  const s = STATUS[line.status];

  async function voidDocument(id: string) {
    setError(null);
    const r = await api.pdde.voidDocument(schoolId, id);
    if (!r.ok) return setError(describe(r.error));
    onChanged();
  }

  return (
    <li className="rounded-[var(--r-lg)] border border-line bg-white px-5 py-4 sm:px-6" data-status={line.status}>
      <div className="flex flex-wrap items-start gap-x-5 gap-y-2">
        <div className="min-w-0 flex-1 basis-60">
          <p className="text-sub text-ink-2">
            {formatDayLong(line.postedOn)} · {line.accountNickname}
          </p>
          <p className="font-semibold [overflow-wrap:anywhere]">{line.memo}</p>
          <p className="text-sub text-ink-2">
            {c
              ? [KIND_LABELS[c.kind], programName(c.program, c.programLabel), c.economicCategory ? ECONOMIC_LABELS[c.economicCategory] : "", c.object ?? ""].filter(Boolean).join(" · ")
              : "Ainda sem classificação"}
          </p>
        </div>
        <p className={`text-[1.125rem] font-bold tabular-nums ${line.amountCents < 0 ? "text-bad" : "text-ok"}`}>{formatBRL(line.amountCents)}</p>
        <StatusPill tone={s.tone}>{s.label}</StatusPill>
      </div>
      {line.looksLikeFee && line.amountCents < 0 && <p className="mt-2 text-sub text-warn">Parece uma tarifa do banco: a conta do PDDE não paga tarifas.</p>}
      {isExpense && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-sub text-ink-2">
            Comprovado {formatBRL(line.documentedCents)} de {formatBRL(-line.amountCents)}
          </p>
          <ul className="mt-1 space-y-1">
            {line.documents
              .filter((d) => !d.voided)
              .map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-x-3 text-sub">
                  <span className="[overflow-wrap:anywhere]">
                    {DOC_LABELS[d.docKind]} {d.docNumber ? `nº ${d.docNumber}` : ""} · {d.vendor} · {formatBRL(d.amountCents)}
                    {d.stamped ? "" : " · sem o carimbo do programa"}
                  </span>
                  <Button variant="plain" size="md" onClick={() => void voidDocument(d.id)} aria-label={`Anular o documento de ${d.vendor}`} className="rounded-full!">
                    Anular
                  </Button>
                </li>
              ))}
          </ul>
        </div>
      )}
      <div aria-live="polite">{error && <p role="alert" className="mt-2 rounded-[var(--r-md)] bg-bad-soft px-4 py-2 text-sub font-medium text-bad">{error}</p>}</div>
      <div className="mt-3 flex flex-wrap gap-3">
        <Button variant="chip" size="md" onClick={() => setClassifying(true)} className="min-h-11">
          {c ? "Mudar a classificação" : "Classificar"}
        </Button>
        {isExpense && line.status !== "DONE" && (
          <Button variant="chip" size="md" onClick={() => setDocumenting(true)} className="min-h-11">
            Registrar documento
          </Button>
        )}
      </div>
      {classifying && (
        <ClassifyModal
          schoolId={schoolId}
          line={line}
          onClose={() => setClassifying(false)}
          onDone={() => {
            setClassifying(false);
            onChanged();
          }}
        />
      )}
      {documenting && (
        <DocumentModal
          schoolId={schoolId}
          line={line}
          onClose={() => setDocumenting(false)}
          onDone={() => {
            setDocumenting(false);
            onChanged();
          }}
        />
      )}
    </li>
  );
}

// --- the area ------------------------------------------------------------------------------------

const link = "inline-flex min-h-11 items-center rounded-full border border-line-strong bg-white px-5 text-sub font-semibold text-brand-800 hover:bg-bg";

interface Props {
  schoolId: string;
}

/**
 * PDDE: a prestação de contas do dinheiro federal. A conta do PDDE (cadastrada em Conciliação, com a finalidade
 * PDDE) tem o extrato importado; aqui cada lançamento é classificado (programa, custeio ou capital, objeto) e cada
 * despesa é comprovada por documentos, como na tela do BB Gestão Ágil. A situação de cada linha e o saldo de cada
 * programa vêm da API; o site não soma nada. O relatório do ano é o espelho que a escola guarda.
 */
export function PddeArea({ schoolId }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const options = recentPeriods(latest, 36);
  const [period, setPeriod] = useState(options[0]!);
  const year = Number(period.slice(0, 4));
  const [version, setVersion] = useState(0);
  // What was loaded stays on the screen while it is read again (after a save); it is hidden only when
  // the month changes, so the list never blinks away under the person's hands.
  const [month, setMonth] = useState<{ period: string; res: ApiResult<PddeMonth> } | null>(null);
  const [summary, setSummary] = useState<{ year: number; res: ApiResult<PddeYear> } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.pdde.month(schoolId, period).then((res) => !cancelled && setMonth({ period, res }));
    void api.pdde.year(schoolId, year).then((res) => !cancelled && setSummary({ year, res }));
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, year, version]);

  const m = month?.period === period ? month.res : null;
  const y = summary?.year === year ? summary.res : null;
  const refresh = () => setVersion((n) => n + 1);

  return (
    <div>
      <section aria-label="PDDE do ano" className="mb-8 rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
        <h2 className="text-heading">PDDE: {year}</h2>
        <p className="mt-1 max-w-[62ch] text-sub text-ink-2">
          Classifique cada lançamento da conta do PDDE e comprove as despesas com documentos, como na prestação de contas do BB Gestão Ágil. Aqui fica o espelho que a escola guarda; o envio oficial é feito no sistema do banco e pela prefeitura.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-4">
          <div className="min-w-0 basis-56">
            <SelectField id="pdde-period" label="Mês" value={period} onChange={(e) => setPeriod(e.target.value)}>
              {options.map((p) => (
                <option key={p} value={p}>
                  {periodLabel(p)}
                </option>
              ))}
            </SelectField>
          </div>
          <a className={link} href={pddeReportHref(schoolId, year, "pdf")} download>
            Relatório do ano (PDF)
          </a>
          <a className={link} href={pddeReportHref(schoolId, year, "csv")} download>
            Relatório do ano (planilha)
          </a>
        </div>
        {y && !y.ok && <p className="mt-4 text-sub text-ink-2">Não foi possível carregar o resumo do ano.</p>}
        {y && y.ok && (
          <>
            <Alerts alerts={y.data.alerts} />
            {y.data.programs.length > 0 && (
              <ul aria-label="Saldo por programa" className="mt-4 grid gap-3 sm:grid-cols-2">
                {y.data.programs.map((p) => (
                  <li key={`${p.program}-${p.programLabel ?? ""}`} className="rounded-[var(--r-md)] border border-line px-4 py-3">
                    <p className="font-semibold">{programName(p.program, p.programLabel)}</p>
                    <p className="text-sub text-ink-2">
                      Recebido {formatBRL(p.receivedCents)} · custeio {formatBRL(p.spentCusteioCents)} · capital {formatBRL(p.spentCapitalCents)}
                    </p>
                    <p className="text-[1.125rem] font-bold tabular-nums text-brand-800">Saldo {formatBRL(p.balanceCents)}</p>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      {!m && (
        <p role="status" aria-busy="true" className="text-sub text-ink-2">
          Carregando o PDDE…
        </p>
      )}
      {m && !m.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {m.error.status === 403 ? "O seu perfil não mexe no PDDE desta escola." : describe(m.error)}
        </p>
      )}
      {m && m.ok && m.data.accounts.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center">
          <h2 className="text-heading">Falta a conta do PDDE</h2>
          <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">
            Em <a className="font-semibold underline" href="/painel/conciliacao">Conciliação</a>, cadastre a conta do PDDE (finalidade PDDE) e importe o extrato dela. Os lançamentos aparecem aqui para classificar.
          </p>
        </div>
      )}
      {m && m.ok && m.data.accounts.length > 0 && m.data.lines.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center">
          <h2 className="text-heading">Nenhum lançamento em {periodLabel(period)}</h2>
          <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">Importe o extrato deste mês da conta do PDDE em Conciliação, ou escolha outro mês.</p>
        </div>
      )}
      {m && m.ok && m.data.lines.length > 0 && (
        <ul aria-label="Lançamentos da conta do PDDE" className="space-y-3">
          {m.data.lines.map((line) => (
            <LineItem key={line.lineId} schoolId={schoolId} line={line} onChanged={refresh} />
          ))}
        </ul>
      )}
    </div>
  );
}
