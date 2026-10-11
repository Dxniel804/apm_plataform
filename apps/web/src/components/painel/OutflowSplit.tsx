import type { StatementSummary } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";

/**
 * "Saídas pagas" (Figma): quanto do que saiu foi reembolso e quanto foi despesa. Os valores sao colunas de
 * statement_summary; a porcentagem e so a razao de duas colunas para o desenho e para o texto.
 */
export function OutflowSplit({ summary: s }: { summary: StatementSummary }) {
  const total = s.totalOutCents;
  const parts = [
    { key: "reimbursements", label: "Reembolsos", cents: s.reimbursementsOutCents, color: "var(--series-base)" },
    { key: "expenses", label: "Despesas", cents: s.expensesOutCents, color: "var(--series-after)" },
  ];
  const ratio = (cents: number) => (total > 0 ? (cents / total) * 100 : 0);

  return (
    <section aria-labelledby="outflow-title" className="rounded-[var(--r-lg)] border border-line p-5 sm:p-7">
      <h3 id="outflow-title" className="text-[1.125rem] font-normal tracking-normal text-ink-2 sm:text-[1.375rem]">
        Saídas pagas
      </h3>
      <p className="mt-0.5 text-foot text-ink-2">Total do mês: {formatBRL(total)}</p>

      {total > 0 ? (
        <>
          <div aria-hidden="true" className="mt-7 flex h-7 gap-[3px] overflow-hidden rounded-full">
            {parts.map((p) => (
              <span key={p.key} style={{ width: `${ratio(p.cents)}%`, background: p.color }} className="block h-full min-w-1" />
            ))}
          </div>
          <ul className="mt-7 space-y-4">
            {parts.map((p) => (
              <li key={p.key} className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-3 text-[1.0625rem] text-ink sm:text-[1.1875rem]">
                  <span aria-hidden="true" className="size-4 shrink-0 rounded-[5px]" style={{ background: p.color }} />
                  {p.label}
                </span>
                <span className="text-right text-[1.0625rem] font-bold tabular-nums text-ink sm:text-[1.1875rem]">
                  {formatBRL(p.cents)} · {Math.round(ratio(p.cents))}%
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-6 text-body text-ink-2">Nenhuma saída paga neste mês.</p>
      )}
    </section>
  );
}
