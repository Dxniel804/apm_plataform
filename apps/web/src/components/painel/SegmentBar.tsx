import type { ReactNode } from "react";

/** Escala de azuis da marca, do mais escuro ao mais claro: no maximo 4 trechos por barra (o validador de paleta nao separa 5). */
export const BLUES = ["#182c7a", "#346ae3", "#7bb3ff", "#c9dcff"] as const;

export interface Segment {
  key: string;
  label: string;
  /** So o tamanho do trecho (dinheiro, quantidade...): o texto que vale e o de `value`. */
  weight: number;
  value: string;
  /** Texto apagado ao lado do valor, como "(2 itens)". */
  meta?: string;
  color: string;
  /** Com ele a linha da legenda vira botao (abre o detalhe). */
  onClick?: () => void;
  /** Quando ha botao, o que ele abre (para o leitor de tela). */
  popup?: "dialog";
}

/**
 * Uma barra so, grossa, dividida em trechos: a porcentagem de cada trecho em cima, a legenda embaixo (bolinha, nome,
 * valor e, apagado, o detalhe). Da para entender so de olhar, sem frase corrida. A porcentagem e a razao entre os pesos,
 * so para o desenho; os valores escritos vem de quem usa. Trechos sem peso nao aparecem na barra nem na legenda.
 */
export function SegmentBar({ segments, label }: { segments: Segment[]; label: string }) {
  const shown = segments.filter((s) => s.weight > 0);
  const total = shown.reduce((sum, s) => sum + s.weight, 0);
  if (total <= 0) return null;
  const pct = (s: Segment) => (s.weight / total) * 100;

  return (
    <div>
      {/* a porcentagem fica no comeco do trecho; trecho estreito demais nao leva rotulo (a legenda diz tudo) */}
      <div aria-hidden="true" className="flex gap-0.5 text-sub font-semibold text-brand-800">
        {shown.map((s) => (
          <span key={s.key} style={{ width: `${pct(s)}%` }} className="min-w-1 overflow-hidden whitespace-nowrap">
            {pct(s) >= 9 ? `${Math.round(pct(s))}%` : ""}
          </span>
        ))}
      </div>
      <div
        role="img"
        aria-label={`${label}: ${shown.map((s) => `${s.label} ${Math.round(pct(s))}%`).join(", ")}`}
        className="mt-1.5 flex h-7 gap-0.5 overflow-hidden rounded-[10px]"
      >
        {shown.map((s) => (
          <span key={s.key} className="block h-full min-w-1" style={{ width: `${pct(s)}%`, background: s.color }} />
        ))}
      </div>

      <ul className="mt-4 space-y-0.5">
        {shown.map((s) => {
          const row: ReactNode = (
            <>
              <span aria-hidden="true" className="size-3.5 shrink-0 self-center rounded-full" style={{ background: s.color }} />
              <span className="min-w-0 flex-1 text-body leading-snug text-ink">{s.label}</span>
              <span className="shrink-0 text-right sm:min-w-28 text-body font-semibold tabular-nums text-brand-800">{s.value}</span>
              {s.meta && <span className="w-20 shrink-0 text-sub text-ink-2">{s.meta}</span>}
            </>
          );
          return (
            <li key={s.key}>
              {s.onClick ? (
                <button type="button" aria-haspopup={s.popup} onClick={s.onClick} className="flex w-full items-baseline gap-3 rounded-[var(--r-md)] px-3 py-2 text-left transition-colors hover:bg-pill">
                  {row}
                </button>
              ) : (
                <div className="flex items-baseline gap-3 px-3 py-2">{row}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
