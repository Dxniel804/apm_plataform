import type { ReactNode } from "react";

export interface Kpi {
  key: string;
  icon: ReactNode;
  label: string;
  value: ReactNode;
  note?: ReactNode;
}

/**
 * Tres numeros lado a lado (o primeiro, o principal, um pouco mais largo): o mesmo bloco da dashboard da APM e do PDDE.
 * No celular o principal ocupa a primeira linha e os outros dois dividem a segunda. @container: a largura que conta e a
 * do bloco, nao a da janela (a barra lateral come espaco).
 */
export function KpiCards({ label, items }: { label: string; items: [Kpi, Kpi, Kpi] }) {
  return (
    <section aria-label={label} className="@container">
      <div className="grid grid-cols-2 overflow-hidden rounded-[var(--r-lg)] border border-line @xl:grid-cols-[1.35fr_1fr_1fr] [&>div]:border-line [&>div:nth-child(3)]:border-l [&>div:nth-child(n+2)]:border-t @xl:[&>div:nth-child(n+2)]:border-l @xl:[&>div:nth-child(n+2)]:border-t-0">
        {items.map((item, i) => (
          <div key={item.key} className={`min-w-0 px-4 py-5 @xl:px-6 @xl:py-6 ${i === 0 ? "col-span-2 @xl:col-span-1" : ""}`}>
            <h2 className="flex items-center gap-2.5 text-[1rem] font-normal text-ink">
              <span aria-hidden="true" className="text-ink-2">
                {item.icon}
              </span>
              {item.label}
            </h2>
            <p className="mt-3 text-kpi text-brand-800">{item.value}</p>
            {item.note && <div className="mt-1 text-foot text-ink-2">{item.note}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}
