import type { ReactNode } from "react";
import { formatBRL } from "@/lib/money";
import { FIELD_LABELS, IDENTIFICATION_FIELDS, type IdentificationValues } from "@/lib/validation";

export type Step = "amount" | "identification" | "review" | "pix";

export const STEP_LABELS: Record<Step, string> = {
  amount: "Valor",
  identification: "Seus dados",
  review: "Revisão",
  pix: "Pix",
};

/** Progresso real: as etapas formam uma sequencia. Mostra as etapas que a escola usa. `labels` troca o nome de uma etapa (o pedido de uma campanha chama "Valor" de "Produtos"). */
export function StepProgress({ steps, current, labels }: { steps: Step[]; current: Step; labels?: Partial<Record<Step, string>> }) {
  const index = Math.max(0, steps.indexOf(current));
  return (
    <div className="mb-6">
      <ol className="flex gap-1.5" aria-hidden="true">
        {steps.map((step, i) => (
          <li key={step} className={`h-[5px] flex-1 rounded-full transition-colors ${i <= index ? "bg-brand-800" : "bg-line-strong"}`} />
        ))}
      </ol>
      <p className="mt-2 text-foot text-ink-3" aria-live="polite">
        Etapa {index + 1} de {steps.length}: <span className="font-semibold text-brand-800">{labels?.[current] ?? STEP_LABELS[current]}</span>
      </p>
    </div>
  );
}

export function SummaryCard({
  schoolName,
  amountCents,
  description,
  identification,
  children,
  heading = "Sua contribuição para",
  label = "Resumo da contribuição",
  lines,
}: {
  schoolName: string;
  amountCents: number | null;
  description: string | null;
  identification: IdentificationValues;
  children?: ReactNode;
  /** O que aparece antes do nome da escola. */
  heading?: string;
  /** Nome acessivel do resumo. */
  label?: string;
  /** O que o carrinho tem agora (nome, quantidade, subtotal), so no pedido de uma campanha. */
  lines?: Array<{ name: string; quantity: number; totalCents: number }>;
}) {
  const filled = IDENTIFICATION_FIELDS.filter((field) => identification[field]);
  return (
    <aside
      aria-label={label}
      className="rounded-[var(--r-lg)] border border-line bg-[#f8fafe] p-6"
    >
      <p className="text-sub text-ink-2">{heading}</p>
      <p className="text-headline text-brand-800">{schoolName}</p>
      <p className="mt-5 text-[2.25rem] font-bold leading-none tracking-[-0.03em] text-brand-800">
        {amountCents === null ? "R$ —" : formatBRL(amountCents)}
      </p>
      <p className="mt-1.5 min-h-5 text-sub text-ink-2">{description ?? (lines ? "Escolha os produtos para começar." : "Escolha o valor para começar.")}</p>
      {lines && lines.length > 0 && (
        <ul aria-label="Produtos do pedido" className="mt-5 space-y-2 border-t border-line pt-4 text-sub">
          {lines.map((line) => (
            <li key={line.name} className="flex justify-between gap-4">
              <span className="min-w-0 text-ink-2 [overflow-wrap:anywhere]">
                {line.quantity} × {line.name}
              </span>
              <span className="shrink-0 font-semibold tabular-nums text-brand-800">{formatBRL(line.totalCents)}</span>
            </li>
          ))}
        </ul>
      )}
      {filled.length > 0 && (
        <dl className="mt-5 space-y-2 border-t border-line pt-4 text-sub">
          {filled.map((field) => (
            <div key={field} className="flex justify-between gap-4">
              <dt className="text-ink-2">{FIELD_LABELS[field]}</dt>
              <dd className="min-w-0 text-right font-semibold text-brand-800">{identification[field]}</dd>
            </div>
          ))}
        </dl>
      )}
      {children}
    </aside>
  );
}

/** Barra de acao: fixa embaixo no celular (alcance do polegar), inline no desktop. */
export function StickyActions({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 z-20 -mx-5 mt-8 flex items-stretch gap-3 border-t border-line bg-white px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-3.5 sm:-mx-8 sm:justify-end sm:px-8 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:px-0 lg:py-0">
      {children}
    </div>
  );
}
