"use client";

import { useState } from "react";
import { TrendDownIcon, TrendUpIcon } from "@/components/ui/icons";
import type { SeriesPoint } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { periodLabel } from "@/lib/statement-labels";

const MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const short = (period: string) => MONTHS_SHORT[Number(period.slice(5, 7)) - 1] ?? period;
const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
/** "R$ 2,5 mil" nos rotulos do eixo (o valor exato esta no tooltip e na tabela). */
const axisLabel = (cents: number) => (cents === 0 ? "R$ 0" : `R$ ${compact.format(cents / 100)}`);

/** Passo "redondo" (1, 2, 2,5 ou 5 vezes uma potencia de 10, em centavos) que cabe `span` em duas faixas. */
function niceStep(span: number): number {
  const raw = Math.max(span, 100) / 2;
  const base = 10 ** Math.floor(Math.log10(raw));
  return (([1, 2, 2.5, 5, 10].find((f) => f * base >= raw) ?? 10) * base);
}

interface Pt {
  x: number;
  y: number;
}

/** Curva suave que nunca passa dos valores (monotona, Fritsch-Carlson): o saldo nao "ondula" entre dois meses. */
function smoothPath(pts: Pt[]): string {
  const n = pts.length;
  if (n === 1) return `M${pts[0]!.x},${pts[0]!.y}`;
  const dx = pts.slice(1).map((p, i) => p.x - pts[i]!.x);
  const m = pts.slice(1).map((p, i) => (p.y - pts[i]!.y) / dx[i]!);
  const t = pts.map((_, i) => (i === 0 ? m[0]! : i === n - 1 ? m[n - 2]! : m[i - 1]! * m[i]! <= 0 ? 0 : (m[i - 1]! + m[i]!) / 2));
  m.forEach((mk, k) => {
    if (mk === 0) {
      t[k] = 0;
      t[k + 1] = 0;
      return;
    }
    const a = t[k]! / mk;
    const b = t[k + 1]! / mk;
    const s = a * a + b * b;
    if (s > 9) {
      const tau = 3 / Math.sqrt(s);
      t[k] = tau * a * mk;
      t[k + 1] = tau * b * mk;
    }
  });
  let d = `M${pts[0]!.x},${pts[0]!.y}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[i]!;
    const p1 = pts[i + 1]!;
    const h = dx[i]! / 3;
    d += ` C${p0.x + h},${p0.y + t[i]! * h} ${p1.x - h},${p1.y - t[i + 1]! * h} ${p1.x},${p1.y}`;
  }
  return d;
}

/**
 * "Saldo em caixa mes a mes": o saldo no FIM de cada mes, para a gestao ver de relance se o caixa cresce ou encolhe.
 * Os numeros vem do servidor (cada mes e o resumo daquele mes); a altura da curva e so desenho. Entradas e saidas do
 * mes ja estao nos cartoes de cima; aqui elas so aparecem ao passar o mouse e na tabela de texto, que diz a mesma
 * coisa para quem nao enxerga o grafico. Sem biblioteca: um SVG para a curva e HTML para pontos, rotulos e hover
 * (assim o texto e os pontos nao se deformam quando o desenho estica).
 */
export function BalanceTrend({ points: all }: { points: SeriesPoint[] }) {
  const [active, setActive] = useState<number | null>(null);

  // Meses vazios no comeco (antes de a escola usar o sistema) so achatam a curva em zero: ficam de fora, no minimo 3.
  const firstUsed = all.findIndex((p) => p.totalInCents > 0 || p.totalOutCents > 0);
  const points = all.slice(firstUsed < 0 ? 0 : Math.min(firstUsed, Math.max(all.length - 3, 0)));
  const empty = points.every((p) => p.totalInCents === 0 && p.totalOutCents === 0 && p.closingBalanceCents === 0);

  // Variacao do ultimo mes contra o anterior (sempre sobre a serie inteira, nao so a parte desenhada).
  const last = all[all.length - 1];
  const prev = all[all.length - 2];
  const delta = last && prev ? last.closingBalanceCents - prev.closingBalanceCents : null;

  // Escala com valores redondos no eixo (0, 2 mil, 4 mil...): o zero (ou o menor saldo, se negativo) e o maior saldo cabem sempre.
  const values = points.map((p) => p.closingBalanceCents);
  const step = niceStep(Math.max(...values, -Math.min(...values)));
  const top = Math.max(1, Math.ceil(Math.max(...values) / step)) * step;
  const bottom = Math.min(0, Math.floor(Math.min(...values) / step)) * step;
  const yOf = (cents: number) => ((top - cents) / (top - bottom)) * 100;
  const xOf = (i: number) => ((i + 0.5) / points.length) * 100;
  const pts: Pt[] = points.map((p, i) => ({ x: xOf(i), y: yOf(p.closingBalanceCents) }));
  const zeroY = yOf(0);
  const line = smoothPath(pts);
  const area = `${line} L${pts[pts.length - 1]!.x},${zeroY} L${pts[0]!.x},${zeroY} Z`;
  const ticks = Array.from({ length: Math.round((top - bottom) / step) + 1 }, (_, i) => top - i * step);
  const shown = active === null ? null : points[active]!;

  return (
    <section aria-labelledby="trend-title" className="rounded-[var(--r-lg)] border border-line p-6">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <h2 id="trend-title" className="text-[1rem] font-medium text-ink">
          Saldo em caixa mês a mês
        </h2>
        {delta !== null && delta !== 0 && prev && (
          <p className="inline-flex items-center gap-1.5 rounded-full bg-pill px-3 py-1 text-sub font-semibold text-brand-800">
            {delta > 0 ? <TrendUpIcon size={16} aria-hidden="true" /> : <TrendDownIcon size={16} aria-hidden="true" />}
            {delta > 0 ? "Subiu" : "Caiu"} {formatBRL(Math.abs(delta))} desde {periodLabel(prev.period).split(" de ")[0]}
          </p>
        )}
      </div>

      {empty ? (
        <p className="mt-5 text-body text-ink-2">Ainda não há movimento nesses meses. Quando houver, a curva aparece aqui.</p>
      ) : (
        <div
          role="img"
          aria-label={`Saldo em caixa no fim de cada mês: ${points.map((p) => `${short(p.period)} ${formatBRL(p.closingBalanceCents)}`).join(", ")}. Os valores estão na tabela abaixo.`}
          className="mt-6"
        >
          <div className="flex gap-3">
            {/* eixo vertical: so tres rotulos, recessivos */}
            <div aria-hidden="true" className="relative h-48 w-16 shrink-0 whitespace-nowrap text-right text-foot text-ink-3 sm:h-56">
              {ticks.map((v) => (
                <span key={v} className="absolute right-0 -translate-y-1/2 tabular-nums" style={{ top: `${yOf(v)}%` }}>
                  {axisLabel(v)}
                </span>
              ))}
            </div>

            <div className="relative h-48 min-w-0 flex-1 sm:h-56" onMouseLeave={() => setActive(null)}>
              {ticks.map((v) => (
                <span key={v} aria-hidden="true" className={`absolute inset-x-0 border-t ${v === 0 ? "border-line-strong" : "border-dashed border-line"}`} style={{ top: `${yOf(v)}%` }} />
              ))}

              <svg aria-hidden="true" focusable="false" viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
                <defs>
                  <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--series-in)" stopOpacity="0.32" />
                    <stop offset="100%" stopColor="var(--series-in)" stopOpacity="0.02" />
                  </linearGradient>
                </defs>
                <path d={area} fill="url(#trend-fill)" />
                <path d={line} fill="none" stroke="var(--series-in)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                {active !== null && <line x1={pts[active]!.x} x2={pts[active]!.x} y1={0} y2={100} stroke="var(--line-strong)" strokeWidth={1} vectorEffect="non-scaling-stroke" />}
              </svg>

              {/* pontos em HTML (o SVG estica, o circulo nao pode esticar); o ultimo mes e o destaque */}
              {pts.map((p, i) => {
                const isLast = i === pts.length - 1;
                const size = isLast || active === i ? 14 : 10;
                return (
                  <span
                    key={points[i]!.period}
                    aria-hidden="true"
                    className="absolute rounded-full border-2 border-white shadow-sm"
                    style={{ left: `${p.x}%`, top: `${p.y}%`, width: size, height: size, marginLeft: -size / 2, marginTop: -size / 2, background: isLast ? "var(--series-base)" : "var(--series-in)" }}
                  />
                );
              })}

              {/* uma area de toque por mes, bem maior que o ponto; funciona com mouse e teclado */}
              <div className="absolute inset-0 flex">
                {points.map((p, i) => (
                  <button
                    key={p.period}
                    type="button"
                    onMouseEnter={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive(null)}
                    aria-label={`${periodLabel(p.period)}: saldo ${formatBRL(p.closingBalanceCents)}`}
                    className="h-full flex-1 cursor-default rounded-md outline-offset-[-2px] focus-visible:outline-2 focus-visible:outline-brand-600"
                  />
                ))}
              </div>

              {shown && (
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute z-10 w-max max-w-[16rem] rounded-[var(--r-md)] border border-line-strong bg-white px-3.5 py-2.5 text-foot shadow-lg"
                  style={{
                    left: `${pts[active!]!.x}%`,
                    top: `${Math.max(pts[active!]!.y - 4, 0)}%`,
                    transform: `translate(${pts[active!]!.x < 25 ? "-12%" : pts[active!]!.x > 75 ? "-88%" : "-50%"}, -100%)`,
                  }}
                >
                  <p className="font-semibold capitalize text-ink">{periodLabel(shown.period)}</p>
                  <p className="mt-1 text-[0.9375rem] font-bold tabular-nums text-brand-800">Saldo {formatBRL(shown.closingBalanceCents)}</p>
                  <p className="mt-1 tabular-nums text-ink-2">
                    Entradas {formatBRL(shown.totalInCents)} · saídas {formatBRL(shown.totalOutCents)}
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="mt-2 flex gap-3" aria-hidden="true">
            <span className="w-16 shrink-0" />
            <div className="flex min-w-0 flex-1">
              {points.map((p, i) => (
                <p key={p.period} className={`flex-1 text-center text-foot ${i === points.length - 1 ? "font-semibold text-ink" : "text-ink-2"}`}>
                  {short(p.period)}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      <details className="mt-3">
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
