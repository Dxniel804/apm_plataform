import { Amount } from "@/components/ui/Amount";
import { StatusPill } from "@/components/ui/StatusPill";
import type { Receipt } from "@/lib/api/types";
import { formatDateTime, formatMonthYear } from "@/lib/format";
import { formatBRL } from "@/lib/money";
import { pixStatusView } from "@/lib/status";
import { SchoolMonogram } from "./SchoolMonogram";

const METHOD_LABELS: Record<string, string> = {
  PIX: "Pix",
  CASH: "Dinheiro",
  TRANSFER: "Transferência",
  OTHER: "Outra forma",
};

/**
 * Selo de confirmacao: circulo azul base com o check, num halo claro. So aparece quando o status
 * devolvido pela camada de dados e PAID. As duas partes (`data-part`) sao tracos visiveis em qualquer
 * momento (nenhuma animacao parte de algo invisivel; ver os detectores em e2e/).
 */
export function PaidStamp({ animate = false, size = 84 }: { animate?: boolean; size?: number }) {
  return (
    <div aria-hidden="true" data-testid="paid-stamp" className={animate ? "pop" : undefined} style={{ width: size, height: size }}>
      <svg viewBox="0 0 84 84" width={size} height={size} fill="none">
        <circle data-part="ring" cx="42" cy="42" r="41" fill="var(--pill)" stroke="var(--pill-line)" strokeWidth="1" />
        <circle cx="42" cy="42" r="30" fill="var(--color-brand-800)" />
        <path data-part="check" d="M30 42.5 38.5 51 54 34" stroke="#ffffff" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

/** Comprovante de contribuicao: cartao sobrio com o valor em destaque e os dados em linhas separadas. */
export function ReceiptCard({ receipt, headingLevel = 2 }: { receipt: Receipt; headingLevel?: 2 | 3 }) {
  const status = pixStatusView(receipt.status);
  const Heading = `h${headingLevel}` as "h2" | "h3";
  const rows: Array<[string, string]> = [
    ["Número", receipt.referenceCode],
    ["Forma de pagamento", METHOD_LABELS[receipt.method] ?? receipt.method],
    ["Pago em", formatDateTime(receipt.paidAt)],
    ...(receipt.referenceMonth ? ([["Referente a", formatMonthYear(receipt.referenceMonth)]] as Array<[string, string]>) : []),
  ];

  return (
    <article
      className="rounded-[var(--r-lg)] border border-line bg-white p-[1.375rem]"
      aria-label={`Comprovante número ${receipt.referenceCode}`}
    >
      <header className="flex items-center gap-3">
        <SchoolMonogram name={receipt.schoolName} size={42} />
        <div className="min-w-0">
          <Heading className="text-[1rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere]">{receipt.schoolName}</Heading>
          <p className="text-[0.75rem] leading-snug text-ink-2">
            {receipt.campaignTitle ? `Comprovante de pedido · ${receipt.campaignTitle}` : "Comprovante de contribuição"}
          </p>
        </div>
      </header>

      <div className="my-4 border-t border-line" aria-hidden="true" />

      <p className="text-foot text-ink-2">Valor</p>
      <p className="mt-0.5">
        <Amount
          cents={receipt.amountCents}
          className="text-[2.75rem] font-bold leading-none tracking-[-0.02em] text-brand-800"
          centsClassName="text-[1.375rem] font-semibold"
        />
      </p>

      {receipt.items.length > 0 && (
        <ul aria-label="Produtos do pedido" className="mt-5 space-y-2 border-t border-line pt-4 text-sub">
          {receipt.items.map((line) => (
            <li key={line.name} className="flex items-baseline justify-between gap-4">
              <span className="min-w-0 text-ink-2 [overflow-wrap:anywhere]">
                {line.quantity} × {line.name}
              </span>
              <span className="shrink-0 font-medium tabular-nums text-ink">{formatBRL(line.unitPriceCents * line.quantity)}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="my-4 border-t border-line" aria-hidden="true" />

      <dl className="space-y-3.5 text-sub">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-5">
            <dt className="shrink-0 text-ink-2">{label}</dt>
            <dd className="min-w-0 text-right font-semibold text-ink [overflow-wrap:anywhere]">{value}</dd>
          </div>
        ))}
        <div className="flex items-center justify-between gap-5">
          <dt className="text-ink-2">Situação</dt>
          <dd>
            <StatusPill tone={status.tone}>{status.label}</StatusPill>
          </dd>
        </div>
      </dl>
    </article>
  );
}
