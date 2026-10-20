"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { StatusPill } from "@/components/ui/StatusPill";
import { SelectField, TextField } from "@/components/ui/TextField";
import { FormsSetup } from "@/components/pdde/FormsSetup";
import { api } from "@/lib/api";
import type { ApiError, ApiResult } from "@/lib/api/types";
import {
  pddeBensHref,
  pddeConciliacaoHref,
  pddeDemonstrativoHref,
  pddeReportHref,
  type PddeAlert,
  type PddeDocKind,
  type PddeEconomic,
  type PddeKind,
  type PddeLine,
  type PddeMonth,
  type PddeProgram,
  type PddeProgramBalance,
  type PddeYear,
} from "@/lib/api/pdde";
import { PDDE_OBJECTS, suggestCredit, suggestObject } from "@/lib/pdde-objects";
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
  TRANSFER: "Repasse do FNDE",
  YIELD: "Rendimento",
  EXPENSE: "Compra",
  RETURN_TO_FNDE: "Devolução ao FNDE",
  TAX_TO_EEX: "Imposto pago à prefeitura",
  REFUND: "Estorno",
  INELIGIBLE: "Não pode ser paga com o PDDE",
};
const DOC_LABELS: Record<PddeDocKind, string> = { NFE: "Nota fiscal eletrônica (NF-e)", INVOICE: "Fatura", RECEIPT: "Recibo", OTHER: "Outro documento" };
const ECONOMIC_LABELS: Record<PddeEconomic, string> = { CUSTEIO: "Custeio", CAPITAL: "Capital" };

const programName = (program: PddeProgram | null, label: string | null) => (program === null ? "" : program === "OUTRO" ? (label ?? PROGRAM_LABELS.OUTRO) : PROGRAM_LABELS[program]);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function describe(error: ApiError): string {
  if (error.kind === "network" || error.kind === "timeout") return "Sem conexão com o servidor. Nada foi alterado.";
  switch (error.code) {
    case "document_key_used":
      return "Esta nota já comprova outro lançamento.";
    case "line_is_not_an_expense":
      return "Só saídas recebem nota.";
    case "rule_violation":
      return "Não foi possível salvar: confira o tipo e o valor das notas.";
    case "validation_error":
      return "Confira os dados. A chave da NF-e tem 44 números.";
    case "permission_denied":
      return "Você não tem permissão para mexer no PDDE.";
    default:
      return error.status === 404 ? "Este lançamento não está mais aqui. Atualize a página." : "Não foi possível concluir. Tente de novo.";
  }
}

/** Avisos curtos. A contagem de pendências fica no resumo, nao aqui. */
function alertText(a: PddeAlert): string | null {
  const where = a.program ? programName(a.program, null) : "";
  switch (a.code) {
    case "fee_on_pdde_account":
      return `${plural(a.count, "tarifa bancária", "tarifas bancárias")} na conta do PDDE (${formatBRL(a.cents)}). Peça o estorno ao banco.`;
    case "spent_over_received":
      return `${where}: ${formatBRL(a.cents)} a mais em ${a.economicCategory === "CAPITAL" ? "capital" : "custeio"} do que entrou.`;
    case "year_end_reconciliation":
      return `Falta o extrato de dezembro em ${plural(a.count, "conta", "contas")}.`;
    case "deadline":
      return `Prazo na Secretaria: ${a.date ? formatDayLong(a.date) : "30/04"}.`;
    case "deadline_passed":
      return `O prazo de ${a.date ? formatDayLong(a.date) : "30/04"} passou.`;
    case "pending_lines":
      return null;
  }
}

function Alerts({ alerts }: { alerts: PddeAlert[] }) {
  const texts = alerts.map(alertText).filter((t): t is string => t !== null);
  if (texts.length === 0) return null;
  return (
    <ul aria-label="Atenção" className="mt-4 space-y-2">
      {texts.map((t) => (
        <li key={t} className="rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
          {t}
        </li>
      ))}
    </ul>
  );
}

function Money({ label, cents, onChange, hint }: { label: string; cents: number; onChange: (v: number) => void; hint?: string }) {
  return <TextField label={label} name={label} prefix="R$" inputMode="numeric" autoComplete="off" placeholder="0,00" hint={hint} value={cents === 0 ? "" : formatBRLNumber(cents)} onChange={(e) => onChange(centsFromDigits(e.target.value))} />;
}

/** Custeio ou capital em dois botoes: vem escolhido pelo sistema, um clique troca. */
function EconomicChips({ value, onChange }: { value: PddeEconomic | ""; onChange: (v: PddeEconomic) => void }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sub font-semibold">Conta como</legend>
      <div className="flex gap-2">
        {(Object.keys(ECONOMIC_LABELS) as PddeEconomic[]).map((c) => (
          <label key={c} className={`inline-flex min-h-11 cursor-pointer items-center rounded-full border px-5 text-sub font-semibold ${value === c ? "border-brand-800 bg-brand-800 text-white" : "border-line-strong bg-white text-brand-800"}`}>
            <input type="radio" name="pdde-economic" value={c} checked={value === c} onChange={() => onChange(c)} className="sr-only" />
            {ECONOMIC_LABELS[c]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// --- classify ------------------------------------------------------------------------------------

const OTHER_KINDS: PddeKind[] = ["RETURN_TO_FNDE", "TAX_TO_EEX", "INELIGIBLE", "REFUND"];
const CREDIT_KINDS: PddeKind[] = ["TRANSFER", "YIELD", "REFUND"];

function ClassifyModal({ schoolId, line, programs, onClose, onDone }: { schoolId: string; line: PddeLine; programs: PddeProgramBalance[]; onClose: () => void; onDone: () => void }) {
  const credit = line.amountCents > 0;
  const current = line.classification;
  const onlyProgram = programs.length === 1 ? programs[0]! : null;
  const creditHint = credit ? suggestCredit(line.memo) : null;
  const objectHint = !credit ? suggestObject(line.memo) : null;

  const [kind, setKind] = useState<PddeKind>(current?.kind ?? (credit ? (creditHint?.kind ?? "TRANSFER") : "EXPENSE"));
  const [objectLabel, setObjectLabel] = useState(current?.kind === "EXPENSE" ? (current.object ?? "") : (objectHint?.label ?? ""));
  const [program, setProgram] = useState<PddeProgram>(current?.program ?? creditHint?.program ?? onlyProgram?.program ?? "BASICO");
  const [label, setLabel] = useState(current?.programLabel ?? onlyProgram?.programLabel ?? "");
  const [category, setCategory] = useState<PddeEconomic | "">(current?.economicCategory ?? creditHint?.economic ?? objectHint?.economic ?? "");
  const [note, setNote] = useState(current?.note ?? "");
  const [paymentNumber, setPaymentNumber] = useState(current?.paymentNumber ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsProgram = kind === "TRANSFER" || kind === "EXPENSE" || kind === "YIELD" || kind === "RETURN_TO_FNDE";
  const needsCategory = needsProgram;
  const showProgram = needsProgram && (credit || onlyProgram === null);

  // Debit: one list, the purchases first and then the other kinds of outflow. Choosing a purchase sets custeio or capital.
  const choice = kind === "EXPENSE" ? `obj:${objectLabel}` : `kind:${kind}`;
  function choose(value: string) {
    if (value.startsWith("obj:")) {
      const found = PDDE_OBJECTS.find((o) => o.label === value.slice(4));
      setKind("EXPENSE");
      setObjectLabel(found?.label ?? "");
      if (found) setCategory(found.economic);
    } else {
      setKind(value.slice(5) as PddeKind);
      setObjectLabel("");
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (kind === "EXPENSE" && objectLabel === "") return setError("Escolha o que foi comprado.");
    if (needsCategory && category === "") return setError("Escolha custeio ou capital.");
    if (needsProgram && program === "OUTRO" && label.trim() === "") return setError("Diga o nome do programa.");
    setBusy(true);
    setError(null);
    const r = await api.pdde.classify(schoolId, line.lineId, {
      kind,
      ...(needsProgram ? { program, ...(program === "OUTRO" ? { programLabel: label.trim() } : {}) } : {}),
      ...(category !== "" && needsProgram ? { economicCategory: category } : {}),
      ...(kind === "EXPENSE" ? { object: objectLabel } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
      ...(paymentNumber.trim() && (kind === "EXPENSE" || kind === "RETURN_TO_FNDE") ? { paymentNumber: paymentNumber.trim() } : {}),
    });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onDone();
  }

  return (
    <FormModal title={credit ? "O que entrou" : "O que foi comprado"} intro={`${formatDayLong(line.postedOn)} · ${formatBRL(line.amountCents)} · ${line.memo}`} onClose={onClose} busy={busy}>
      <form method="post" onSubmit={(e) => void submit(e)} className="space-y-5">
        {credit ? (
          <SelectField id="pdde-kind" label="Tipo" value={kind} onChange={(e) => setKind(e.target.value as PddeKind)}>
            {CREDIT_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </SelectField>
        ) : (
          <SelectField id="pdde-what" label="Item" value={choice} onChange={(e) => choose(e.target.value)}>
            <option value="obj:">Escolha</option>
            <optgroup label="Compra">
              {PDDE_OBJECTS.map((o) => (
                <option key={o.label} value={`obj:${o.label}`}>
                  {o.label}
                </option>
              ))}
            </optgroup>
            <optgroup label="Outra saída">
              {OTHER_KINDS.map((k) => (
                <option key={k} value={`kind:${k}`}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </optgroup>
          </SelectField>
        )}
        {showProgram && (
          <SelectField id="pdde-program" label="Programa" value={program} onChange={(e) => setProgram(e.target.value as PddeProgram)}>
            {(Object.keys(PROGRAM_LABELS) as PddeProgram[]).map((p) => (
              <option key={p} value={p}>
                {PROGRAM_LABELS[p]}
              </option>
            ))}
          </SelectField>
        )}
        {needsProgram && program === "OUTRO" && showProgram && <TextField label="Nome do programa" name="program-label" maxLength={60} value={label} onChange={(e) => setLabel(e.target.value)} />}
        {needsCategory && (kind !== "EXPENSE" || objectLabel !== "") && <EconomicChips value={category} onChange={setCategory} />}
        {(kind === "EXPENSE" || kind === "RETURN_TO_FNDE") && (
          <details>
            <summary className="cursor-pointer text-sub font-semibold text-brand-800">Mais dados</summary>
            <div className="mt-3 space-y-4">
              <TextField label="Nº do cheque ou da ordem bancária" optional name="payment-number" maxLength={40} value={paymentNumber} onChange={(e) => setPaymentNumber(e.target.value)} />
              <TextField label="Observação" optional name="note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          </details>
        )}
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
  const [stamped, setStamped] = useState(true);
  const [taxId, setTaxId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [specification, setSpecification] = useState("");
  const capital = line.classification?.economicCategory === "CAPITAL";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(issuedOn)) return setError("Informe a data da nota.");
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
      ...(taxId.trim() ? { vendorTaxId: taxId.trim() } : {}),
      ...(capital && quantity.trim() ? { quantity: Number(quantity) } : {}),
      ...(capital && specification.trim() ? { specification: specification.trim() } : {}),
    });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onDone();
  }

  return (
    <FormModal title="Anexar nota" intro={`${line.memo} · falta ${formatBRL(Math.max(left, 0))}`} onClose={onClose} busy={busy}>
      <form method="post" onSubmit={(e) => void submit(e)} className="space-y-5">
        <SelectField id="pdde-doc-kind" label="Tipo" value={docKind} onChange={(e) => setDocKind(e.target.value as PddeDocKind)}>
          {(Object.keys(DOC_LABELS) as PddeDocKind[]).map((k) => (
            <option key={k} value={k}>
              {DOC_LABELS[k]}
            </option>
          ))}
        </SelectField>
        {docKind === "NFE" && <TextField label="Chave da NF-e (44 números)" name="access-key" inputMode="numeric" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Fornecedor" name="vendor" maxLength={120} value={vendor} onChange={(e) => setVendor(e.target.value)} />
          <TextField label="Data da nota" name="issued-on" type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} />
        </div>
        <Money label="Valor da nota" cents={cents} onChange={setCents} />
        {capital && (
          <div className="grid gap-4 sm:grid-cols-3">
            <TextField label="Quantidade" optional name="quantity" inputMode="numeric" maxLength={7} value={quantity} onChange={(e) => setQuantity(e.target.value.replace(/\D/g, ""))} />
            <TextField className="sm:col-span-2" label="Qual é o bem" optional name="specification" maxLength={200} value={specification} onChange={(e) => setSpecification(e.target.value)} />
          </div>
        )}
        <details>
          <summary className="cursor-pointer text-sub font-semibold text-brand-800">Mais dados</summary>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <TextField label="Número da nota" optional name="number" maxLength={40} value={number} onChange={(e) => setNumber(e.target.value)} />
            <TextField label="CNPJ ou CPF do fornecedor" optional name="tax-id" inputMode="numeric" autoComplete="off" maxLength={24} value={taxId} onChange={(e) => setTaxId(e.target.value)} />
          </div>
        </details>
        <label className="flex items-start gap-3 text-sub">
          <input type="checkbox" checked={stamped} onChange={(e) => setStamped(e.target.checked)} className="mt-1 size-5" />
          <span>Tem o carimbo &quot;Pagos com recursos do&quot; e o programa</span>
        </label>
        <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
        <FormButtons onCancel={onClose} submitLabel="Anexar" pending={busy} />
      </form>
    </FormModal>
  );
}

// --- a line --------------------------------------------------------------------------------------

function lineState(line: PddeLine): { tone: "warning" | "info" | "success"; label: string } {
  const c = line.classification;
  if (!c) return { tone: "warning", label: "Classificar" };
  if (c.kind === "EXPENSE" && line.status !== "DONE") return { tone: line.status === "PARTIAL" ? "info" : "warning", label: "Falta nota" };
  return { tone: "success", label: "Pronto" };
}

function LineItem({ schoolId, line, programs, onChanged }: { schoolId: string; line: PddeLine; programs: PddeProgramBalance[]; onChanged: () => void }) {
  const [classifying, setClassifying] = useState(false);
  const [documenting, setDocumenting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const c = line.classification;
  const isExpense = c?.kind === "EXPENSE";
  const credit = line.amountCents > 0;
  const s = lineState(line);
  // An income line whose text already says the program and custeio or capital is confirmed in one click.
  const hint = credit && !c ? suggestCredit(line.memo) : null;
  const onlyProgram = programs.length === 1 ? programs[0]!.program : null;
  const readyProgram = hint ? (hint.program ?? onlyProgram) : null;
  const canConfirm = hint !== null && readyProgram !== null && hint.economic !== null;

  async function confirm() {
    if (!hint || !readyProgram || !hint.economic) return;
    setBusy(true);
    setError(null);
    const only = programs.length === 1 ? programs[0]! : null;
    const r = await api.pdde.classify(schoolId, line.lineId, {
      kind: hint.kind,
      program: readyProgram,
      ...(readyProgram === "OUTRO" && only?.programLabel ? { programLabel: only.programLabel } : {}),
      economicCategory: hint.economic,
    });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onChanged();
  }

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
          <p className="text-sub text-ink-2">{formatDayLong(line.postedOn)}</p>
          <p className="font-semibold [overflow-wrap:anywhere]">{line.memo}</p>
          <p className="text-sub text-ink-2">
            {c
              ? [KIND_LABELS[c.kind], programName(c.program, c.programLabel), c.economicCategory ? ECONOMIC_LABELS[c.economicCategory] : "", c.object ?? ""].filter(Boolean).join(" · ")
              : canConfirm
                ? `Sugestão: ${[programName(readyProgram, null), ECONOMIC_LABELS[hint!.economic!]].join(" · ")}`
                : ""}
          </p>
        </div>
        <p className={`text-[1.125rem] font-bold tabular-nums ${line.amountCents < 0 ? "text-bad" : "text-ok"}`}>{formatBRL(line.amountCents)}</p>
        <StatusPill tone={s.tone}>{s.label}</StatusPill>
      </div>
      {line.looksLikeFee && line.amountCents < 0 && <p className="mt-2 text-sub text-warn">Parece tarifa: o PDDE não paga tarifa.</p>}
      {isExpense && line.documents.some((d) => !d.voided) && (
        <ul className="mt-3 space-y-1 border-t border-line pt-3">
          {line.documents
            .filter((d) => !d.voided)
            .map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-x-3 text-sub">
                <span className="[overflow-wrap:anywhere]">
                  {DOC_LABELS[d.docKind]} {d.docNumber ? `nº ${d.docNumber}` : ""} · {d.vendor} · {formatBRL(d.amountCents)}
                  {d.stamped ? "" : " · sem carimbo"}
                </span>
                <Button variant="plain" size="md" onClick={() => void voidDocument(d.id)} aria-label={`Anular a nota de ${d.vendor}`} className="rounded-full!">
                  Anular
                </Button>
              </li>
            ))}
        </ul>
      )}
      {isExpense && line.status !== "DONE" && <p className="mt-2 text-sub text-ink-2">Falta {formatBRL(-line.amountCents - line.documentedCents)}</p>}
      <div aria-live="polite">{error && <p role="alert" className="mt-2 rounded-[var(--r-md)] bg-bad-soft px-4 py-2 text-sub font-medium text-bad">{error}</p>}</div>
      <div className="mt-3 flex flex-wrap gap-3">
        {canConfirm && (
          <Button variant="chip" size="md" disabled={busy} onClick={() => void confirm()} className="min-h-11">
            Confirmar
          </Button>
        )}
        {isExpense && line.status !== "DONE" && (
          <Button variant="chip" size="md" onClick={() => setDocumenting(true)} className="min-h-11">
            Anexar nota
          </Button>
        )}
        <Button variant={canConfirm || !c || (isExpense && line.status !== "DONE") ? "secondary" : "chip"} size="md" onClick={() => setClassifying(true)} className="min-h-11">
          {c ? "Mudar" : credit ? "Escolher" : "O que foi comprado?"}
        </Button>
      </div>
      {classifying && (
        <ClassifyModal
          schoolId={schoolId}
          line={line}
          programs={programs}
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

type Step = "in" | "out" | "deliver";

interface Props {
  schoolId: string;
}

/**
 * PDDE em tres passos: o que entrou (o texto do extrato ja diz programa e custeio ou capital, so confirmar), o que
 * foi gasto (escolhe-se o item comprado; o site deduz custeio ou capital) e o que entregar. A escola imprime os
 * formularios do FNDE e leva o papel a Secretaria de Educacao, que presta contas no sistema: nada e enviado daqui.
 * A situacao de cada linha e o saldo de cada programa vem da API; o site nao soma nada.
 */
export function PddeArea({ schoolId }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const options = recentPeriods(latest, 36);
  const [period, setPeriod] = useState(options[0]!);
  const [step, setStep] = useState<Step>("in");
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

  const lines = m && m.ok ? m.data.lines : [];
  const incoming = lines.filter((l) => l.amountCents > 0);
  const outgoing = lines.filter((l) => l.amountCents < 0);
  const inTodo = incoming.filter((l) => !l.classification).length;
  const outTodo = outgoing.filter((l) => lineState(l).label !== "Pronto").length;
  const programs = y && y.ok ? y.data.programs : [];
  const noAccount = m && m.ok && m.data.accounts.length === 0;

  const tab = (id: Step, text: string, todo: number) => (
    <button
      key={id}
      type="button"
      role="tab"
      aria-selected={step === id}
      onClick={() => setStep(id)}
      className={`inline-flex min-h-11 items-center gap-2 rounded-full border px-5 text-sub font-semibold ${step === id ? "border-brand-800 bg-brand-800 text-white" : "border-line-strong bg-white text-brand-800 hover:bg-bg"}`}
    >
      {text}
      {todo > 0 && <span className={`rounded-full px-2 py-0.5 text-[0.75rem] ${step === id ? "bg-white text-brand-800" : "bg-warn-soft text-warn"}`}>{todo}</span>}
    </button>
  );

  return (
    <div>
      <section aria-label="PDDE" className="mb-6 rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 className="text-heading">PDDE {year}</h2>
          <div className="min-w-0 basis-56">
            <SelectField id="pdde-period" label="Mês" value={period} onChange={(e) => setPeriod(e.target.value)}>
              {options.map((p) => (
                <option key={p} value={p}>
                  {periodLabel(p)}
                </option>
              ))}
            </SelectField>
          </div>
        </div>
        <div role="tablist" aria-label="Passos do PDDE" className="mt-4 flex flex-wrap gap-2">
          {tab("in", "1 · Entrou", inTodo)}
          {tab("out", "2 · Gastei", outTodo)}
          {tab("deliver", "3 · Entregar", 0)}
        </div>
      </section>

      {!m && (
        <p role="status" aria-busy="true" className="text-sub text-ink-2">
          Carregando…
        </p>
      )}
      {m && !m.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {m.error.status === 403 ? "O seu perfil não mexe no PDDE desta escola." : describe(m.error)}
        </p>
      )}
      {noAccount && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center">
          <h2 className="text-heading">Falta a conta do PDDE</h2>
          <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">
            Cadastre-a em <a className="font-semibold underline" href="/painel/conciliacao">Conciliação</a> e importe o extrato.
          </p>
        </div>
      )}

      {m && m.ok && !noAccount && step !== "deliver" && (
        <>
          {(step === "in" ? incoming : outgoing).length === 0 ? (
            <div className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center">
              <h2 className="text-heading">{step === "in" ? "Nenhuma entrada" : "Nenhuma saída"} em {periodLabel(period)}</h2>
              <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">Importe o extrato em Conciliação ou escolha outro mês.</p>
            </div>
          ) : (
            <ul aria-label="Lançamentos da conta do PDDE" className="space-y-3">
              {(step === "in" ? incoming : outgoing).map((line) => (
                <LineItem key={line.lineId} schoolId={schoolId} line={line} programs={programs} onChanged={refresh} />
              ))}
            </ul>
          )}
        </>
      )}

      {step === "deliver" && (
        <section aria-label="Entregar" className="rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
          {y && !y.ok && <p className="text-sub text-ink-2">Não foi possível carregar o ano.</p>}
          {!y && <p className="text-sub text-ink-2">Carregando…</p>}
          {y && y.ok && (
            <>
              <p className={`rounded-[var(--r-md)] px-4 py-3 text-body font-semibold ${y.data.pendingCount > 0 ? "bg-warn-soft text-warn" : "bg-ok-soft text-ok"}`}>
                {y.data.pendingCount > 0 ? `Faltam ${plural(y.data.pendingCount, "lançamento", "lançamentos")}` : "Tudo pronto para entregar"}
              </p>
              <Alerts alerts={y.data.alerts} />
              {programs.length > 0 && (
                <ul aria-label="Saldo por programa" className="mt-5 grid gap-3 sm:grid-cols-2">
                  {programs.map((p) => (
                    <li key={`${p.program}-${p.programLabel ?? ""}`} className="rounded-[var(--r-md)] border border-line px-4 py-3">
                      <p className="font-semibold">{programName(p.program, p.programLabel)}</p>
                      <p className="text-sub text-ink-2">
                        Entrou {formatBRL(p.receivedCents)} · Saldo {formatBRL(p.balanceCents)}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <a className={link} href={pddeDemonstrativoHref(schoolId, year, p.program, p.programLabel)} download>
                          Demonstrativo (PDF)
                        </a>
                        {p.spentCapitalCents > 0 && (
                          <a className={link} href={pddeBensHref(schoolId, year, p.program, p.programLabel)} download>
                            Relação de bens (PDF)
                          </a>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-5 flex flex-wrap gap-2">
                {y.data.accounts.map((a) => (
                  <a key={a.id} className={link} href={pddeConciliacaoHref(schoolId, year, a.id)} download>
                    Conciliação bancária{y.data.accounts.length > 1 ? `: ${a.nickname}` : ""} (PDF)
                  </a>
                ))}
                <a className={link} href={pddeReportHref(schoolId, year, "pdf")} download>
                  Lista dos lançamentos (PDF)
                </a>
                <a className={link} href={pddeReportHref(schoolId, year, "csv")} download>
                  Lista dos lançamentos (planilha)
                </a>
              </div>
              <p className="mt-5 text-sub text-ink-2">Levar junto: extratos, notas e recibos, atas.</p>
              <FormsSetup schoolId={schoolId} year={year} />
            </>
          )}
        </section>
      )}
    </div>
  );
}
