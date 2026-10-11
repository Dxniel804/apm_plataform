"use client";

import type { Ref } from "react";
import { Button } from "@/components/ui/Button";
import { BagIcon } from "@/components/ui/icons";
import { formatBRL } from "@/lib/money";
import { FIELD_LABELS, IDENTIFICATION_FIELDS, type IdentificationValues } from "@/lib/validation";
import { StickyActions } from "./FlowChrome";

interface ReviewStepProps {
  schoolName: string;
  description: string;
  amountCents: number;
  identification: IdentificationValues;
  submitting: boolean;
  error: string | null;
  headingRef: Ref<HTMLHeadingElement>;
  onEditAmount: () => void;
  onEditIdentification: (() => void) | null;
  onBack: () => void;
  onSubmit: () => void;
}

function Row({ label, value, onEdit, editLabel }: { label: string; value: string; onEdit?: (() => void) | null; editLabel?: string }) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-[1.1rem] border border-field-border bg-white px-4 py-2.5">
      <div className="min-w-0">
        <span className="block text-foot text-ink-2">{label}</span>
        <span className="block text-body font-medium text-brand-800 [overflow-wrap:anywhere]">{value}</span>
      </div>
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          aria-label={editLabel}
          className="inline-flex min-h-11 shrink-0 items-center rounded-full px-3 text-sub font-bold text-brand-800 hover:bg-info-soft"
        >
          Alterar
        </button>
      )}
    </li>
  );
}

export function ReviewStep({
  schoolName,
  description,
  amountCents,
  identification,
  submitting,
  error,
  headingRef,
  onEditAmount,
  onEditIdentification,
  onBack,
  onSubmit,
}: ReviewStepProps) {
  const filled = IDENTIFICATION_FIELDS.filter((field) => identification[field]);
  return (
    <div>
      <h2 ref={headingRef} tabIndex={-1} className="text-title outline-none">
        Confira antes de pagar
      </h2>
      <p className="mt-2 max-w-[52ch] text-body text-ink-2">
        Se estiver tudo certo, vamos gerar o Pix. Você só paga depois de abrir o app do seu banco.
      </p>

      <p className="mt-6 text-sub font-bold text-brand-800">Informações</p>
      <ul aria-label="Resumo da contribuição" className="mt-2 space-y-2.5 rounded-[var(--r-lg)] border border-field-border p-3 sm:p-4">
        <Row label="Escola" value={schoolName} />
        <Row label="Contribuição" value={description} onEdit={onEditAmount} editLabel="Alterar o valor" />
        <Row label="Valor" value={formatBRL(amountCents)} />
        {filled.map((field) => (
          <Row
            key={field}
            label={FIELD_LABELS[field]}
            value={identification[field] ?? ""}
            onEdit={onEditIdentification}
            editLabel={`Alterar ${FIELD_LABELS[field].toLowerCase()}`}
          />
        ))}
      </ul>

      <p className="mt-4 flex items-start gap-2.5 text-sub text-ink-2">
        <BagIcon size={18} className="mt-0.5 shrink-0" />
        O Pix vai direto para a conta da APM. A plataforma não guarda o dinheiro e quem confirma o pagamento é o banco.
      </p>

      <div aria-live="polite">
        {error && (
          <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
            {error}
          </p>
        )}
      </div>

      <StickyActions>
        <Button variant="secondary" className="shrink-0 sm:min-w-32" onClick={onBack} disabled={submitting}>
          Voltar
        </Button>
        <Button variant="solid" className="flex-1 sm:min-w-56 sm:flex-none" onClick={onSubmit} disabled={submitting} aria-busy={submitting}>
          {submitting ? "Gerando o Pix…" : `Gerar Pix de ${formatBRL(amountCents)}`}
        </Button>
      </StickyActions>
    </div>
  );
}
