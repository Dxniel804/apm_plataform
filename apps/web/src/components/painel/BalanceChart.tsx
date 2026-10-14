import type { CSSProperties } from "react";
import type { StatementSummary } from "@/lib/api/types";
import { TrendUpIcon } from "@/components/ui/icons";
import { formatBRLNumber } from "@/lib/money";

interface Bar {
  key: string;
  label: string;
  /** Texto do valor, como no Figma: "397,10", "+2.201,48", "-240,00". */
  text: string;
  /** Extremos do trecho desenhado (so a posicao da barra; o texto vem da API). */
  from: number;
  to: number;
  color: string;
  /** Onde a linha de ligacao com a proxima barra encosta (so desenho). */
  carry?: number;
}

/**
 * "Composicao do saldo" (Figma): do saldo inicial ate o saldo apos os reembolsos pendentes. Cada barra e um trecho
 * flutuante; os numeros escritos sao as colunas de statement_summary, sem conta nenhuma (a soma abaixo so decide
 * ONDE a barra fica no desenho). Em telas largas sao colunas; no celular viram linhas com barras horizontais.
 */
export function BalanceChart({ summary: s }: { summary: StatementSummary }) {
  const bars: Bar[] = [
    { key: "open", label: "Saldo inicial", text: formatBRLNumber(s.openingBalanceCents), from: 0, to: s.openingBalanceCents, color: "var(--series-base)" },
    {
      key: "in",
      label: "Entradas",
      text: `+${formatBRLNumber(s.totalInCents)}`,
      from: s.openingBalanceCents,
      to: s.openingBalanceCents + s.totalInCents,
      color: "var(--series-in)",
    },
    {
      key: "out",
      label: "Saídas",
      text: `-${formatBRLNumber(s.totalOutCents)}`,
      from: s.closingBalanceCents,
      to: s.closingBalanceCents + s.totalOutCents,
      color: "var(--series-out)",
    },
    { key: "close", label: "Saldo em caixa", text: formatBRLNumber(s.closingBalanceCents), from: 0, to: s.closingBalanceCents, color: "var(--series-base)" },
    {
      key: "pending",
      label: "A reembolsar",
      text: `-${formatBRLNumber(s.pendingReimbursementsCents)}`,
      from: s.balanceAfterPendingCents,
      to: s.closingBalanceCents,
      color: "var(--series-out)",
    },
    { key: "after", label: "Após pendências", text: formatBRLNumber(s.balanceAfterPendingCents), from: 0, to: s.balanceAfterPendingCents, color: "var(--series-after)" },
  ];

  // Linha de ligacao: o nivel em que cada barra termina e a seguinte comeca (so posicao no desenho).
  const carries: Record<string, number> = {
    open: s.openingBalanceCents,
    in: s.openingBalanceCents + s.totalInCents,
    out: s.closingBalanceCents,
    close: s.closingBalanceCents,
    pending: s.balanceAfterPendingCents,
  };

  const ends = bars.flatMap((b) => [b.from, b.to]);
  const min = Math.min(0, ...ends);
  const max = Math.max(1, ...ends);
  const place = (v: number) => ((v - min) / (max - min)) * 100;

  return (
    <section aria-labelledby="balance-chart-title" className="@container rounded-[var(--r-lg)] border border-line p-6">
      <h3 id="balance-chart-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
        <TrendUpIcon size={20} className="text-ink-2" aria-hidden="true" />
        Composição do saldo
      </h3>
      <p className="mt-0.5 text-foot text-ink-2 @[26rem]:pl-[1.875rem]">Do saldo inicial até o caixa final, em reais{min < 0 ? ". A linha tracejada é o zero: abaixo dela o saldo está negativo." : ""}</p>

      <ul className="mt-6 grid gap-3 @[26rem]:grid-cols-6 @[26rem]:gap-0 @[26rem]:pt-4">
        {bars.map((bar) => {
          const lo = Math.min(bar.from, bar.to);
          const hi = Math.max(bar.from, bar.to);
          const negative = hi <= 0 && lo < 0;
          const style = { "--lo": place(lo), "--hi": place(hi), background: negative ? "var(--bad, #c0392b)" : bar.color } as CSSProperties;
          const carry = carries[bar.key];
          const total = bar.from === 0;
          return (
            <li
              key={bar.key}
              className="grid grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_auto] items-center gap-x-3 @[26rem]:flex @[26rem]:flex-col @[26rem]:items-stretch @[26rem]:gap-0"
            >
              {/* trilho (celular) / area da coluna (tela larga) */}
              <span
                aria-hidden="true"
                className="relative col-start-2 row-start-1 h-3.5 rounded-full bg-neutral-soft @[26rem]:order-1 @[26rem]:h-44 @[26rem]:rounded-none @[26rem]:border-b @[26rem]:border-line-strong @[26rem]:bg-transparent sm:@[26rem]:h-52"
              >
                <span
                  style={style}
                  className={`absolute inset-y-0 left-[calc(var(--lo)*1%)] w-[calc((var(--hi)-var(--lo))*1%)] min-w-1 rounded-full @[26rem]:inset-y-auto @[26rem]:bottom-[calc(var(--lo)*1%)] @[26rem]:left-[24%] @[26rem]:h-[calc((var(--hi)-var(--lo))*1%)] @[26rem]:min-h-[3px] @[26rem]:w-auto @[26rem]:min-w-0 @[26rem]:right-[24%] ${total ? "@[26rem]:rounded-b-none @[26rem]:rounded-t-[8px]" : "@[26rem]:rounded-[8px]"}`}
                />
                {min < 0 && (
                  <>
                    {/* A linha do zero: o saldo abaixo dela e negativo (a barra fica na cor das saidas). */}
                    <span
                      style={{ "--zero": place(0) } as CSSProperties}
                      className="absolute hidden border-t border-dashed border-ink-3 @[26rem]:block @[26rem]:bottom-[calc(var(--zero)*1%)] @[26rem]:inset-x-0"
                    />
                  </>
                )}
                {carry !== undefined && (
                  <span
                    style={{ "--lvl": place(carry) } as CSSProperties}
                    className="absolute hidden h-px bg-[#9aa7c7] @[26rem]:block @[26rem]:bottom-[calc(var(--lvl)*1%)] @[26rem]:left-[76%] @[26rem]:w-[48%]"
                  />
                )}
              </span>
              <span className="col-start-1 row-start-1 text-sub leading-tight text-ink-3 @[26rem]:order-2 @[26rem]:mt-3 @[26rem]:min-h-[2.25rem] @[26rem]:px-1 @[26rem]:text-center @[26rem]:text-[0.8125rem]">
                {bar.label}
              </span>
              <span className="col-start-3 row-start-1 text-right text-sub font-bold tabular-nums text-ink @[26rem]:order-3 @[26rem]:mt-1.5 @[26rem]:text-center @[26rem]:text-[0.9375rem]">
                {bar.text}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
