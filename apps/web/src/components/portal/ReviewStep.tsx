"use client";

import type { Ref } from "react";
import { Button } from "@/components/ui/Button";
import { BankIcon } from "@/components/ui/icons";
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
  /** O pedido de uma campanha: uma linha por produto (a soma e o valor). Troca a linha unica "Contribuicao". */
  lines?: Array<{ name: string; quantity: number; unitPriceCents: number }>;
  /** Nome acessivel do botao que volta a escolher o valor ou os produtos. */
  editLabel?: string;
}

function Row({ label, value, onEdit, editLabel, strong }: { label: string; value: string; onEdit?: (() => void) | null; editLabel?: string; strong?: boolean }) {
  return (
    <li className="flex min-h-[3.875rem] items-center justify-between gap-3 border-b border-line py-2.5 last:border-b-0">
      <div className="min-w-0">
        <span className="block text-[0.75rem] text-ink-2">{label}</span>
        <span className={`block font-medium text-brand-800 [overflow-wrap:anywhere] ${strong ? "text-[1.5rem] font-bold leading-tight tracking-[-0.01em]" : "text-body"}`}>{value}</span>
      </div>
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          aria-label={editLabel}
          className="inline-flex min-h-11 shrink-0 items-center rounded-full px-2 text-sub font-semibold text-brand-600 hover:bg-info-soft"
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
  lines,
  editLabel = "Alterar o valor",
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

      <p className="mt-6 text-sub font-semibold text-brand-800">Informações</p>
      <ul aria-label="Resumo da contribuição" className="mt-2 rounded-[var(--r-lg)] border border-line-strong px-[1.125rem]">
        <Row label="Escola" value={schoolName} />
        {lines ? (
          lines.map((line, index) => (
            <Row
              key={line.name}
              label={`${line.quantity} × ${formatBRL(line.unitPriceCents)}`}
              value={line.name}
              onEdit={index === 0 ? onEditAmount : null}
              editLabel={editLabel}
            />
          ))
        ) : (
          <Row label="Contribuição" value={description} onEdit={onEditAmount} editLabel={editLabel} />
        )}
        <Row label={lines ? "Total" : "Valor"} value={formatBRL(amountCents)} strong />
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

      <p className="mt-4 flex items-start gap-3 rounded-[var(--r-md)] bg-info-soft p-3.5 text-foot leading-snug text-ink">
        <BankIcon size={20} className="mt-px shrink-0 text-brand-800" />
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
        <Button variant="secondary" className="w-28 shrink-0 sm:w-auto sm:min-w-32" onClick={onBack} disabled={submitting}>
          Voltar
        </Button>
        <Button variant="solid" className="flex-1 sm:min-w-56 sm:flex-none" onClick={onSubmit} disabled={submitting} aria-busy={submitting}>
          {submitting ? "Gerando o Pix…" : `Gerar Pix de ${formatBRL(amountCents)}`}
        </Button>
      </StickyActions>
    </div>
  );
}
