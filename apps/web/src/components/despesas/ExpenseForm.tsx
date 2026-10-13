"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { FormModal } from "@/components/ui/FormModal";
import { PhotoPicker } from "@/components/ui/PhotoPicker";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ExpenseCategory, ExpenseDetail, OcrSuggestion, PaidBy, PaymentMethod } from "@/lib/api/types";
import { describeExpenseError } from "@/lib/expense-labels";
import { PAYMENT_METHOD_LABELS } from "@/lib/expense-labels";
import { centsFromDigits, formatBRLNumber } from "@/lib/money";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const SCHOOL_TZ = "America/Sao_Paulo";
/** Abaixo disto a leitura de um campo e tratada como duvidosa e a pessoa e avisada. */
const LOW_CONFIDENCE = 0.6;

/** Campos que a leitura da nota preencheu e que a pessoa ainda nao mexeu: "ok" ou "low" (leitura incerta). */
type Suggested = Partial<Record<"amount" | "date" | "vendor" | "description", "ok" | "low">>;

/** YYYY-MM-DD de hoje (ou de um instante) no fuso da escola, para o campo de data. */
export function dayInSchoolZone(instant: Date | string = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: SCHOOL_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(instant));
}

function suggestionHint(mark: "ok" | "low" | undefined): string | undefined {
  if (mark === "low") return "Leitura incerta: confira com atenção.";
  if (mark === "ok") return "Sugerido pela leitura da nota. Confira.";
  return undefined;
}

interface ExpenseFormProps {
  schoolId: string;
  categories: ExpenseCategory[];
  /** Presente = editar este rascunho/correcao. Ausente = nova despesa. */
  expense?: ExpenseDetail;
  /** O servidor tem a leitura automatica de notas ligada? So vale para uma despesa nova. */
  ocrEnabled?: boolean;
  /** Chamado com o id da despesa depois de salvar (e de anexar/enviar, se pedido). */
  onSaved: (expenseId: string, note?: string) => void;
  onCancel: () => void;
}

/**
 * Nova despesa ou edicao de rascunho. O NOME de quem envia nunca e pedido: a API usa o usuario da sessao.
 * O arquivo (nota ou recibo) vai por multipart para a API; o conteudo nao fica em estado, URL, log nem
 * storage do navegador: so o objeto File do campo, ate o envio.
 */
export function ExpenseForm({ schoolId, categories, expense, ocrEnabled = false, onSaved, onCancel }: ExpenseFormProps) {
  const editing = Boolean(expense);
  const [cents, setCents] = useState(expense?.amountCents ?? 0);
  const [day, setDay] = useState(expense ? dayInSchoolZone(expense.occurredAt) : dayInSchoolZone());
  const [chosenCategory, setChosenCategory] = useState(expense?.category.id ?? "");
  // Sem categoria escolhida, vale a primeira da lista (a pessoa ainda pode trocar).
  const categoryId = chosenCategory || categories[0]?.id || "";
  const [description, setDescription] = useState(expense?.description ?? "");
  const [vendor, setVendor] = useState(expense?.vendor ?? "");
  const [purchaseReason, setPurchaseReason] = useState(expense?.purchaseReason ?? "");
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | "">(expense?.paymentMethod ?? "");
  const [paidBy, setPaidBy] = useState<PaidBy>(expense?.paidBy ?? "COLLABORATOR");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [pending, setPending] = useState<"draft" | "send" | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const amountRef = useRef<HTMLInputElement>(null);
  // Leitura da nota (docs/ocr.md): a foto fica so na memoria; o resultado e uma SUGESTAO que a pessoa confere.
  const ocr = ocrEnabled && !editing;
  const [mode, setMode] = useState<"manual" | "ocr">("manual");
  const [photos, setPhotos] = useState<File[]>([]);
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<{ tone: "ok" | "warn"; text: string } | null>(null);
  const [suggested, setSuggested] = useState<Suggested>({});
  const reader = ocr && mode === "ocr";
  const busy = pending !== null || reading;
  const unmark = (field: keyof Suggested) => setSuggested((p) => (p[field] ? { ...p, [field]: undefined } : p));

  function chooseMode(next: "manual" | "ocr") {
    if (next === mode) return;
    setMode(next);
    setPhotos([]);
    setReadNote(null);
    setErrors((p) => ({ ...p, file: "" }));
  }

  function changePhotos(next: File[]) {
    setPhotos(next);
    setReadNote(null);
    setErrors((p) => ({ ...p, file: "" }));
  }

  function applySuggestion(s: OcrSuggestion) {
    const marks: Suggested = {};
    const level = (confidence: number) => (confidence < LOW_CONFIDENCE ? "low" : "ok");
    if (s.amountCents !== null && s.amountCents > 0) {
      setCents(s.amountCents);
      marks.amount = level(s.confidence.amount);
    }
    // Data de depois de hoje nao e aceita pelo campo (max): se a leitura veio assim, fica a que ja estava.
    if (s.occurredOn && s.occurredOn <= dayInSchoolZone()) {
      setDay(s.occurredOn);
      marks.date = level(s.confidence.date);
    }
    if (s.vendor) {
      setVendor(s.vendor);
      marks.vendor = level(s.confidence.vendor);
      if (!description.trim()) {
        setDescription(`Compra em ${s.vendor}`.slice(0, 500));
        marks.description = marks.vendor;
      }
    }
    setSuggested(marks);
    // O que a leitura acabou de preencher nao deve continuar com o erro de "informe o valor" de antes.
    setErrors((p) => ({ ...p, ...(marks.amount && { amount_cents: "" }), ...(marks.date && { occurred_at: "" }), ...(marks.description && { description: "" }) }));
    const found = Object.keys(marks).length;
    if (found === 0) {
      setReadNote({ tone: "warn", text: "Não consegui ler dados desta nota. Tente uma foto mais nítida e de frente, ou preencha os campos à mão: a foto continua anexada." });
    } else if (Object.values(marks).includes("low")) {
      setReadNote({ tone: "warn", text: "Li parte da nota, mas com pouca certeza em alguns campos. Confira os campos marcados antes de salvar." });
    } else {
      setReadNote({ tone: "ok", text: "Leitura concluída. Confira os campos preenchidos antes de salvar." });
    }
  }

  async function readReceipt() {
    const photo = photos[0];
    if (!photo || busy) return;
    setReading(true);
    setReadNote(null);
    setGeneral(null);
    const result = await api.expenses.readReceipt(schoolId, photo);
    setReading(false);
    if (!result.ok) {
      setReadNote({ tone: "warn", text: describeExpenseError(result.error).general ?? "Não foi possível ler a nota. Preencha os campos à mão: a foto continua anexada." });
      return;
    }
    applySuggestion(result.data);
  }

  async function save(sendAfter: boolean) {
    if (pending || reading) return;
    setGeneral(null);
    const problems: Record<string, string> = {};
    if (cents <= 0) problems.amount_cents = "Informe o valor.";
    if (!day) problems.occurred_at = "Informe a data da despesa.";
    if (!categoryId) problems.category_id = "Escolha uma categoria.";
    if (!description.trim()) problems.description = "Descreva a despesa.";
    const file = reader ? photos[0] : fileRef.current?.files?.[0];
    if (file && file.size > MAX_FILE_BYTES) problems.file = "O arquivo é grande demais. O limite é de 10 MB.";
    if (sendAfter) {
      if (purchaseReason.trim().length < 3) problems.purchase_reason = "Informe o motivo da compra (pelo menos 3 letras).";
      if (!paymentMethod) problems.payment_method = "Informe a forma de pagamento.";
      if (!file && !(expense && expense.attachments.length > 0)) problems.file = "Anexe a nota ou o recibo para enviar.";
    }
    setErrors(problems);
    if (Object.keys(problems).length > 0) {
      if (problems.amount_cents) amountRef.current?.focus();
      return;
    }

    setPending(sendAfter ? "send" : "draft");
    const fields = {
      amountCents: cents,
      occurredAt: day,
      categoryId,
      description: description.trim(),
      vendor: vendor.trim() || undefined,
      purchaseReason: purchaseReason.trim() || undefined,
      paymentMethod: paymentMethod || undefined,
    };
    const saved = expense
      ? await api.expenses.update(schoolId, expense.id, fields)
      : await api.expenses.create(schoolId, { ...fields, paidBy });
    if (!saved.ok) {
      const text = describeExpenseError(saved.error);
      setErrors(text.fields);
      setGeneral(text.general);
      setPending(null);
      return;
    }
    const id = saved.data.id;
    let note: string | undefined;
    if (file) {
      const uploaded = await api.expenses.upload(schoolId, id, file, "INVOICE");
      if (!uploaded.ok) {
        const text = describeExpenseError(uploaded.error);
        // O rascunho ja existe: a pessoa continua dele (anexar de novo) em vez de perder o que digitou.
        setPending(null);
        onSaved(id, `Rascunho salvo, mas o arquivo não foi enviado. ${text.general ?? ""}`.trim());
        return;
      }
      note = "Arquivo anexado.";
    }
    if (sendAfter) {
      const sent = await api.expenses.submit(schoolId, id);
      if (!sent.ok) {
        const text = describeExpenseError(sent.error);
        setPending(null);
        onSaved(id, `Rascunho salvo, mas não foi possível enviar. ${text.general ?? ""}`.trim());
        return;
      }
      note = "Despesa enviada para a análise da gestão.";
    } else {
      note = note ?? "Rascunho salvo.";
    }
    setPending(null);
    onSaved(id, note);
  }

  const submitting = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void save(false);
  };

  return (
    <FormModal
      title={editing ? `Editar despesa nº ${expense!.referenceCode}` : "Nova despesa"}
      intro="Quem envia é você, pela sua conta: não pedimos o seu nome. A gestão só vê a despesa depois que você enviar."
      onClose={onCancel}
      busy={busy}
    >
      <form method="post" noValidate onSubmit={submitting} aria-busy={pending !== null} className="space-y-5">
        {ocr && (
          <div role="group" aria-label="Como preencher a despesa" className="flex flex-wrap gap-2.5">
            <button type="button" aria-pressed={mode === "manual"} disabled={busy} onClick={() => chooseMode("manual")} className={chipClass(mode === "manual")}>
              Preencher manualmente
            </button>
            <button type="button" aria-pressed={mode === "ocr"} disabled={busy} onClick={() => chooseMode("ocr")} className={chipClass(mode === "ocr")}>
              Ler a nota (OCR)
            </button>
          </div>
        )}

        {reader && (
          <div className="space-y-4 rounded-[var(--r-md)] bg-info-soft/40 p-4 sm:p-5">
            <p className="max-w-[60ch] text-sub text-ink-2">
              Tire uma foto da nota ou escolha uma da galeria. Os campos abaixo são preenchidos com o que for lido, mas quem confere e salva é você.
            </p>
            <PhotoPicker photos={photos} onChange={changePhotos} max={1} label="Foto da nota" note="(uma foto, PNG, JPEG ou WebP)" disabled={busy} error={errors.file || null} />
            <Button variant="secondary" onClick={() => void readReceipt()} disabled={busy || photos.length === 0} aria-busy={reading} className="rounded-full!">
              {reading ? "Lendo a nota…" : "Ler a nota"}
            </Button>
            <div aria-live="polite">
              {reading && <p role="status" className="text-sub text-ink-2">Lendo a nota. Isso pode levar alguns segundos.</p>}
              {readNote && (
                <p role="status" className={`rounded-[var(--r-md)] px-4 py-3 text-sub font-medium ${readNote.tone === "ok" ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn"}`}>
                  {readNote.text}
                </p>
              )}
            </div>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Valor"
            name="expense-amount"
            prefix="R$"
            inputMode="numeric"
            autoComplete="off"
            placeholder="0,00"
            inputRef={amountRef}
            hint={suggestionHint(suggested.amount)}
            value={cents === 0 ? "" : formatBRLNumber(cents)}
            onChange={(e) => {
              setCents(centsFromDigits(e.target.value));
              setErrors((p) => ({ ...p, amount_cents: "" }));
              unmark("amount");
            }}
            error={errors.amount_cents || undefined}
          />
          <TextField
            label="Data da despesa"
            name="expense-date"
            type="date"
            max={dayInSchoolZone()}
            hint={suggestionHint(suggested.date)}
            value={day}
            onChange={(e) => {
              setDay(e.target.value);
              setErrors((p) => ({ ...p, occurred_at: "" }));
              unmark("date");
            }}
            error={errors.occurred_at || undefined}
          />
        </div>

        <SelectField
          id="expense-category"
          label="Categoria"
          value={categoryId}
          onChange={(e) => setChosenCategory(e.target.value)}
          error={errors.category_id || undefined}
        >
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>

        <TextField
          label="Descrição"
          name="expense-description"
          autoComplete="off"
          maxLength={500}
          hint={suggestionHint(suggested.description)}
          value={description}
          onChange={(e) => {
            setDescription(e.target.value);
            setErrors((p) => ({ ...p, description: "" }));
            unmark("description");
          }}
          error={errors.description || undefined}
        />
        <TextField
          label="Fornecedor"
          optional
          name="expense-vendor"
          autoComplete="off"
          maxLength={200}
          hint={suggestionHint(suggested.vendor)}
          value={vendor}
          onChange={(e) => {
            setVendor(e.target.value);
            unmark("vendor");
          }}
        />
        <TextField
          label="Motivo da compra"
          name="expense-reason"
          autoComplete="off"
          maxLength={500}
          hint="Obrigatório para enviar à gestão."
          value={purchaseReason}
          onChange={(e) => {
            setPurchaseReason(e.target.value);
            setErrors((p) => ({ ...p, purchase_reason: "" }));
          }}
          error={errors.purchase_reason || undefined}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            id="expense-method"
            label="Forma de pagamento"
            value={paymentMethod}
            onChange={(e) => setPaymentMethod(e.target.value as PaymentMethod | "")}
            error={errors.payment_method || undefined}
          >
            <option value="">Escolha…</option>
            {(Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]).map((m) => (
              <option key={m} value={m}>
                {PAYMENT_METHOD_LABELS[m]}
              </option>
            ))}
          </SelectField>
          {!editing && (
            <fieldset>
              <legend className="mb-2 block text-sub font-bold text-brand-800">Quem pagou</legend>
              <label className="flex min-h-11 items-center gap-2 text-body text-ink">
                <input type="radio" name="expense-paid-by" className="size-5 accent-[var(--color-brand-800)]" checked={paidBy === "COLLABORATOR"} onChange={() => setPaidBy("COLLABORATOR")} />
                Eu paguei do meu bolso (reembolso)
              </label>
              <label className="flex min-h-11 items-center gap-2 text-body text-ink">
                <input type="radio" name="expense-paid-by" className="size-5 accent-[var(--color-brand-800)]" checked={paidBy === "APM"} onChange={() => setPaidBy("APM")} />
                Foi paga pela APM
              </label>
            </fieldset>
          )}
        </div>

        {!reader && (
        <div>
          <label htmlFor="expense-file" className="mb-2 block text-sub font-bold text-brand-800">
            Nota ou recibo (PNG, JPEG, WebP ou PDF, até 10 MB)
          </label>
          <input
            id="expense-file"
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,application/pdf"
            onChange={() => setErrors((p) => ({ ...p, file: "" }))}
            className="block w-full text-body text-ink file:mr-3 file:min-h-11 file:rounded-full file:border-0 file:bg-info-soft file:px-5 file:font-semibold file:text-brand-800"
          />
          {errors.file && <p role="alert" className="mt-1.5 text-sub font-medium text-bad">{errors.file}</p>}
        </div>
        )}

        <div aria-live="polite">
          {general && (
            <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
              {general}
            </p>
          )}
        </div>

        <div className="grid gap-3 pt-3 sm:grid-cols-3">
          <Button variant="secondary" onClick={onCancel} disabled={busy} className="rounded-full! order-last sm:order-1">
            Fechar
          </Button>
          <Button type="submit" variant="secondary" disabled={busy} aria-busy={pending === "draft"} className="rounded-full! order-2">
            {pending === "draft" ? "Salvando…" : "Salvar rascunho"}
          </Button>
          <Button onClick={() => void save(true)} disabled={busy} aria-busy={pending === "send"} className="rounded-full! order-1 sm:order-3">
            {pending === "send" ? "Enviando…" : "Salvar e enviar para análise"}
          </Button>
        </div>
      </form>
    </FormModal>
  );
}
