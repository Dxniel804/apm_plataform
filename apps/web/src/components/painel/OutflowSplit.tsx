import { PieIcon } from "@/components/ui/icons";
import type { StatementSummary } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";

/**
 * "Composicao das saidas": quanto do que saiu foi reembolso e quanto foi despesa. Os valores sao colunas de
 * statement_summary; a porcentagem e so a razao de duas colunas para o desenho e para o texto.
 */
export function OutflowSplit({ summary: s }: { summary: StatementSummary }) {
  const total = s.totalOutCents;
  const parts = [
    { key: "reimbursements", label: "Reembolsos", cents: s.reimbursementsOutCents, color: "var(--series-base)" },
    { key: "expenses", label: "Despesas", cents: s.expensesOutCents, color: "var(--series-out)" },
  ];
  const ratio = (cents: number) => (total > 0 ? (cents / total) * 100 : 0);
  const leading = parts.reduce((best, p) => (p.cents > best.cents ? p : best), parts[0]!);

  return (
    <section aria-labelledby="outflow-title" className="flex flex-col rounded-[var(--r-lg)] border border-line p-6">
      <div className="flex items-center justify-between gap-3">
        <h3 id="outflow-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
          <PieIcon size={20} className="text-ink-2" aria-hidden="true" />
          Composição das saídas
        </h3>
        <p className="text-foot text-ink-2">Total do mês: {formatBRL(total)}</p>
      </div>

      {total > 0 ? (
        <div className="mt-auto pt-8">
          <p className="text-[3.25rem] font-semibold leading-none tracking-[-0.02em] text-brand-800">{Math.round(ratio(leading.cents))}%</p>
          <p className="mt-2 text-sub text-ink-2">
            das saídas do mês foram {leading.key === "reimbursements" ? "reembolsos" : "despesas"}
          </p>
          <div aria-hidden="true" className="mt-6 flex h-3 gap-0.5 overflow-hidden rounded-full">
            {parts.map((p) => (
              <span key={p.key} style={{ width: `${ratio(p.cents)}%`, background: p.color }} className="block h-full min-w-1" />
            ))}
          </div>
          <ul className="mt-4 space-y-2">
            {parts.map((p) => (
              <li key={p.key} className="flex items-center gap-2.5 text-sub">
                <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[3px]" style={{ background: p.color }} />
                <span className="flex-1 text-ink">{p.label}</span>
                <span className="font-semibold tabular-nums text-ink">
                  {formatBRL(p.cents)} · {Math.round(ratio(p.cents))}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-6 text-body text-ink-2">Nenhuma saída paga neste mês.</p>
      )}
    </section>
  );
}
