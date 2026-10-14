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
  const empty = points.every((p) => p.totalInCents === 0 && p.totalOutCents === 0);
  const pct = (cents: number) => (cents <= 0 ? 0 : Math.max(2, (cents / max) * 100));
  return (
    <section aria-labelledby="evolution-title" className="rounded-[var(--r-lg)] border border-line p-6">
      <h2 id="evolution-title" className="text-[1rem] font-medium text-ink">
        Evolução do caixa
      </h2>
      <p className="mt-0.5 text-foot text-ink-2">Entradas e saídas dos últimos {points.length} meses.</p>

      {empty ? (
        <p className="mt-5 text-body text-ink-2">Ainda não há movimento nesses meses. Quando houver, as barras aparecem aqui.</p>
      ) : (
        <div role="img" aria-label={`Entradas e saídas dos últimos ${points.length} meses. Os valores estão na tabela abaixo.`} className="mt-5">
          <div className="grid h-48 items-end gap-2 border-b border-line-strong sm:h-56" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
            {points.map((p) => (
              <div key={p.period} className="flex h-full items-end justify-center gap-1 sm:gap-1.5">
                <div title={`Entradas: ${formatBRL(p.totalInCents)}`} className="w-[38%] max-w-9 rounded-t-md" style={{ height: `${pct(p.totalInCents)}%`, background: "var(--series-in)" }} />
                <div title={`Saídas: ${formatBRL(p.totalOutCents)}`} className="w-[38%] max-w-9 rounded-t-md" style={{ height: `${pct(p.totalOutCents)}%`, background: "var(--series-out)" }} />
              </div>
            ))}
          </div>
          <div className="mt-2 grid gap-2" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
            {points.map((p) => (
              <p key={p.period} className="text-center text-foot text-ink-2">
                {short(p.period)}
              </p>
            ))}
          </div>
        </div>
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
