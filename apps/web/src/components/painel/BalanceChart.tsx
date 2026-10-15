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
}

// Desenho da versao larga: 6 colunas de COL_W unidades; cada barra ocupa o miolo da coluna.
const COL_W = 120;
const BAR_X = 29;
const BAR_W = COL_W - 2 * BAR_X;
const CHART_W = COL_W * 6;
const CHART_H = 240;
const PAD_TOP = 4;
const MIN_BAR_H = 3;
const RADIUS = 8;

/** Retangulo com cantos de raio r so em cima, so embaixo ou nos dois lados. */
function barPath(x: number, y: number, w: number, h: number, r: number, round: "top" | "bottom" | "both"): string {
  const rt = round === "bottom" ? 0 : Math.min(r, h / 2, w / 2);
  const rb = round === "top" ? 0 : Math.min(r, h / 2, w / 2);
  return [
    `M${x + rt},${y}`,
    `H${x + w - rt}`,
    rt ? `A${rt},${rt} 0 0 1 ${x + w},${y + rt}` : `L${x + w},${y}`,
    `V${y + h - rb}`,
    rb ? `A${rb},${rb} 0 0 1 ${x + w - rb},${y + h}` : `L${x + w},${y + h}`,
    `H${x + rb}`,
    rb ? `A${rb},${rb} 0 0 1 ${x},${y + h - rb}` : `L${x},${y + h}`,
    `V${y + rt}`,
    rt ? `A${rt},${rt} 0 0 1 ${x + rt},${y}` : `L${x},${y}`,
    "Z",
  ].join(" ");
}

/**
 * "Composicao do saldo" (Figma): do saldo inicial ate o saldo apos os reembolsos pendentes. Cada barra e um trecho
 * flutuante; os numeros escritos sao as colunas de statement_summary, sem conta nenhuma (a soma abaixo so decide
 * ONDE a barra fica no desenho). Em telas largas e um grafico de colunas (SVG, so decoracao); no celular cada etapa
 * vira uma linha com barra horizontal.
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

  // Nivel em que cada barra termina e a seguinte comeca (a linha de ligacao; so posicao no desenho).
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
  /** 0..100 (celular, barras horizontais). */
  const place = (v: number) => ((v - min) / (max - min)) * 100;
  /** Coordenada y no SVG: o menor valor encosta na base, o maior no topo. */
  const plotH = CHART_H - PAD_TOP - 1;
  const yOf = (v: number) => PAD_TOP + (1 - (v - min) / (max - min)) * plotH;

  return (
    <section aria-labelledby="balance-chart-title" className="@container rounded-[var(--r-lg)] border border-line p-6">
      <h3 id="balance-chart-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
        <TrendUpIcon size={20} className="text-ink-2" aria-hidden="true" />
        Composição do saldo
      </h3>
      <p className="mt-0.5 text-foot text-ink-2 @[26rem]:pl-[1.875rem]">Do saldo inicial até o caixa final, em reais{min < 0 ? ". A linha tracejada é o zero: abaixo dela o saldo está negativo." : ""}</p>

      {/* Versao larga: o desenho todo num so SVG (barras, ligacoes, zero e base na mesma escala). */}
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="mt-6 hidden w-full overflow-visible @[26rem]:block"
      >
        {/* base do grafico: o menor nivel desenhado */}
        <line x1={0} x2={CHART_W} y1={CHART_H - 0.5} y2={CHART_H - 0.5} stroke="var(--line-strong)" strokeWidth={1} vectorEffect="non-scaling-stroke" />

        {/* ligacoes entre uma barra e a seguinte */}
        {bars.slice(0, -1).map((bar, i) => {
          const y = yOf(carries[bar.key]!);
          return (
            <line
              key={bar.key}
              x1={i * COL_W + BAR_X + BAR_W}
              x2={(i + 1) * COL_W + BAR_X}
              y1={y}
              y2={y}
              stroke="#9aa7c7"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}

        {bars.map((bar, i) => {
          const lo = Math.min(bar.from, bar.to);
          const hi = Math.max(bar.from, bar.to);
          const negative = hi <= 0 && lo < 0;
          const total = bar.from === 0;
          const h = Math.max(yOf(lo) - yOf(hi), MIN_BAR_H);
          // a barra minima cresce para dentro do espaco acima do nivel mais baixo, nunca para fora do desenho
          const y = Math.min(yOf(hi), CHART_H - h);
          const round = total ? (negative ? "bottom" : "top") : "both";
          return <path key={bar.key} d={barPath(i * COL_W + BAR_X, y, BAR_W, h, RADIUS, round)} fill={negative ? "var(--bad)" : bar.color} />;
        })}

        {/* a linha do zero: UMA so, de ponta a ponta, por cima das barras */}
        {min < 0 && (
          <line
            x1={0}
            x2={CHART_W}
            y1={yOf(0)}
            y2={yOf(0)}
            stroke="var(--ink-3)"
            strokeWidth={1}
            strokeDasharray="4 3"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      <ul className="mt-6 grid gap-3 @[26rem]:mt-3 @[26rem]:grid-cols-6 @[26rem]:gap-0">
        {bars.map((bar) => {
          const lo = Math.min(bar.from, bar.to);
          const hi = Math.max(bar.from, bar.to);
          const negative = hi <= 0 && lo < 0;
          const style = { "--lo": place(lo), "--hi": place(hi), background: negative ? "var(--bad)" : bar.color } as CSSProperties;
          return (
            <li
              key={bar.key}
              className="grid grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_auto] items-center gap-x-3 @[26rem]:flex @[26rem]:flex-col @[26rem]:items-stretch @[26rem]:gap-0"
            >
              {/* trilho (so no celular; na tela larga o SVG acima faz o desenho) */}
              <span aria-hidden="true" className="relative col-start-2 row-start-1 h-3.5 rounded-full bg-neutral-soft @[26rem]:hidden">
                <span
                  style={style}
                  className="absolute inset-y-0 left-[calc(var(--lo)*1%)] w-[calc((var(--hi)-var(--lo))*1%)] min-w-1 rounded-full"
                />
              </span>
              <span className="col-start-1 row-start-1 text-sub leading-tight text-ink-3 @[26rem]:min-h-[2.25rem] @[26rem]:px-1 @[26rem]:text-center @[26rem]:text-[0.8125rem]">
                {bar.label}
              </span>
              <span className="col-start-3 row-start-1 text-right text-sub font-bold tabular-nums text-ink @[26rem]:mt-1.5 @[26rem]:text-center @[26rem]:text-[0.9375rem]">
                {bar.text}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
