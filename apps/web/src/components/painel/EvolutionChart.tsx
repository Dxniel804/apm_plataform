import type { SeriesPoint } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { periodLabel } from "@/lib/statement-labels";

const MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const short = (period: string) => MONTHS_SHORT[Number(period.slice(5, 7)) - 1] ?? period;

/**
 * "Evolucao do caixa": entradas e saidas dos ultimos meses, lado a lado. Os numeros vem do servidor (cada mes e o
 * resumo daquele mes); a altura das barras e so desenho. A tabela de texto abaixo diz a mesma coisa para quem nao
 * enxerga o grafico. Sem biblioteca: SVG.
 */
export function EvolutionChart({ points }: { points: SeriesPoint[] }) {
  const max = Math.max(1, ...points.flatMap((p) => [p.totalInCents, p.totalOutCents]));
  const height = 140;
  const colWidth = 100 / points.length;
  const empty = points.every((p) => p.totalInCents === 0 && p.totalOutCents === 0);
  return (
    <section aria-labelledby="evolution-title" className="rounded-[var(--r-lg)] border border-line p-6">
      <h2 id="evolution-title" className="text-[1rem] font-medium text-ink">
        Evolução do caixa
      </h2>
      <p className="mt-0.5 text-foot text-ink-2">Entradas e saídas dos últimos {points.length} meses.</p>

      {empty ? (
        <p className="mt-5 text-body text-ink-2">Ainda não há movimento nesses meses. Quando houver, as barras aparecem aqui.</p>
      ) : (
        <svg role="img" aria-label={`Entradas e saídas dos últimos ${points.length} meses. Os valores estão na tabela abaixo.`} viewBox={`0 0 100 ${height + 18}`} preserveAspectRatio="none" className="mt-4 h-52 w-full">
          {points.map((p, index) => {
            const x = index * colWidth;
            const inH = (p.totalInCents / max) * height;
            const outH = (p.totalOutCents / max) * height;
            const bar = colWidth * 0.3;
            return (
              <g key={p.period}>
                <rect x={x + colWidth * 0.18} y={height - inH} width={bar} height={inH} fill="var(--series-in)" rx="0.6" />
                <rect x={x + colWidth * 0.18 + bar + 0.8} y={height - outH} width={bar} height={outH} fill="var(--series-out)" rx="0.6" />
                <text x={x + colWidth / 2} y={height + 12} textAnchor="middle" fontSize="4.2" fill="var(--ink-2)">
                  {short(p.period)}
                </text>
              </g>
            );
          })}
          <line x1="0" y1={height} x2="100" y2={height} stroke="var(--line)" strokeWidth="0.4" />
        </svg>
      )}

      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-foot text-ink-2" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: "var(--series-in)" }} /> Entradas</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: "var(--series-out)" }} /> Saídas</span>
      </div>

      <details className="mt-4">
        <summary className="min-h-11 cursor-pointer py-2 text-sub font-semibold text-brand-800">Ver os valores em tabela</summary>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full min-w-[26rem] text-left text-sub">
            <thead className="text-ink-2">
              <tr>
                <th scope="col" className="py-2 pr-3 font-semibold">Mês</th>
                <th scope="col" className="py-2 pr-3 text-right font-semibold">Entradas</th>
                <th scope="col" className="py-2 pr-3 text-right font-semibold">Saídas</th>
                <th scope="col" className="py-2 text-right font-semibold">Saldo em caixa</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {points.map((p) => (
                <tr key={p.period}>
                  <th scope="row" className="py-2 pr-3 font-medium text-ink">{periodLabel(p.period)}</th>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatBRL(p.totalInCents)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatBRL(p.totalOutCents)}</td>
                  <td className="py-2 text-right tabular-nums">{formatBRL(p.closingBalanceCents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
