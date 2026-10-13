"use client";

import { useRef, useState, type FormEvent } from "react";
import { FormButtons, FormWindow } from "@/components/ui/FormModal";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { CashCategory, CashMethod } from "@/lib/api/types";
import { centsFromDigits, formatBRL, formatBRLNumber, MAX_INPUT_CENTS } from "@/lib/money";
import { describeCashError } from "@/lib/public-messages";
import { FIELD_LABELS, validateIdentification, type IdentificationErrors, type IdentificationField } from "@/lib/validation";

const METHODS: Array<[CashMethod, string]> = [
  ["CASH", "Dinheiro"],
  ["TRANSFER", "Transferência"],
  ["OTHER", "Outra forma"],
];
const CATEGORIES: Array<[CashCategory, string]> = [
  ["parent_contribution", "Contribuição de responsável"],
  ["donation", "Doação"],
  ["other_income", "Outra entrada"],
  ["apm_revenue", "Receita da APM"],
];
// So estes campos de identificacao: a gestao nao precisa de e-mail nem telefone aqui.
const FIELDS: IdentificationField[] = ["guardianName", "studentName", "classroom"];
const OPTIONAL = { guardianName: "OPTIONAL", studentName: "OPTIONAL", classroom: "OPTIONAL", contributorEmail: "HIDDEN", contributorPhone: "HIDDEN" } as const;

/**
 * "Registrar contribuicao em dinheiro" (POST /schools/{school_id}/contributions): so para quem tem
 * `contributions:record_cash`. A escola e a do vinculo ativo (a API confere); o tenant nunca vem do
 * formulario. A Idempotency-Key e uma por tentativa: reaproveitada se a rede falhar e repetir, nova
 * quando os dados mudam. So existe em memoria: nunca em URL, log ou storage.
 */
export function CashContributionForm({ schoolId, onRecorded, onClose }: { schoolId: string; onRecorded: () => void; onClose: () => void }) {
  const [cents, setCents] = useState(0);
  const [method, setMethod] = useState<CashMethod>("CASH");
  const [category, setCategory] = useState<CashCategory>("parent_contribution");
  const [values, setValues] = useState<Partial<Record<IdentificationField, string>>>({});
  const [errors, setErrors] = useState<IdentificationErrors>({});
  const [amountError, setAmountError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const attempt = useRef<{ key: string; signature: string } | null>(null);
  const amountRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    setDone(null);
    const identification = validateIdentification(values, OPTIONAL);
    setErrors(identification.errors);
    const amountProblem = cents <= 0 ? "Informe o valor." : cents > MAX_INPUT_CENTS ? "O valor é alto demais." : null;
    setAmountError(amountProblem);
    if (amountProblem) return amountRef.current?.focus();
    if (!identification.ok) return;

    const input = { amountCents: cents, method, categoryKey: category, identification: identification.cleaned };
    const signature = JSON.stringify(input);
    if (attempt.current?.signature !== signature) attempt.current = { key: crypto.randomUUID(), signature };
    setPending(true);
    const result = await api.statement.recordCash(schoolId, input, attempt.current.key);
    setPending(false);
    if (!result.ok) {
      const problems = describeCashError(result.error);
      if (result.error.code === "idempotency_key_reused") attempt.current = null;
      setErrors(problems.fields);
      setAmountError(problems.amount);
      setError(problems.general);
      return;
    }
    attempt.current = null;
    setDone(`Contribuição ${result.data.referenceCode} registrada: ${formatBRL(result.data.amountCents)}.`);
    setCents(0);
    setValues({});
    setErrors({});
    setAmountError(null);
    onRecorded();
  }

  return (
    <FormWindow
      title="Registrar contribuição em dinheiro"
      intro="Para o que a família entregou fora do Pix. O lançamento entra no caixa já pago e fica registrado em seu nome."
      onClose={onClose}
      busy={pending}
      titleId="cash-title"
    >
      <form method="post" noValidate onSubmit={submit} aria-labelledby="cash-title" aria-busy={pending} className="space-y-5">
        <TextField
          label="Valor"
          name="cash-amount"
          prefix="R$"
          inputMode="numeric"
          autoComplete="off"
          placeholder="0,00"
          inputRef={amountRef}
          value={cents === 0 ? "" : formatBRLNumber(cents)}
          onChange={(e) => {
            setCents(centsFromDigits(e.target.value));
            setAmountError(null);
          }}
          error={amountError ?? undefined}
        />

        <div className="grid gap-5 sm:grid-cols-2">
          <SelectField id="cash-method" label="Forma de pagamento" value={method} onChange={(e) => setMethod(e.target.value as CashMethod)}>
            {METHODS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
          <SelectField id="cash-category" label="Tipo de entrada" value={category} onChange={(e) => setCategory(e.target.value as CashCategory)}>
            {CATEGORIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
        </div>

        {FIELDS.map((field) => (
          <TextField
            key={field}
            name={field}
            label={FIELD_LABELS[field]}
            optional
            autoComplete="off"
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="words"
            maxLength={120}
            value={values[field] ?? ""}
            onChange={(e) => {
              setValues((prev) => ({ ...prev, [field]: e.target.value }));
              setErrors((prev) => ({ ...prev, [field]: undefined }));
            }}
            error={errors[field]}
          />
        ))}

        <div aria-live="polite">
          {error && (
            <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
              {error}
            </p>
          )}
          {done && (
            <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">
              {done}
            </p>
          )}
        </div>

        <FormButtons onCancel={onClose} cancelLabel={done ? "Fechar" : "Cancelar"} submitLabel="Salvar" pending={pending} />
      </form>
    </FormWindow>
  );
}
