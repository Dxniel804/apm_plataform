import { WalletIcon } from "@/components/ui/icons";
import { Amount } from "@/components/ui/Amount";
import type { StatementSummary } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";

/**
 * "Para onde foi o dinheiro": o que a APM tinha no mes (saldo inicial mais as entradas) numa barra so, dividido em
 * quanto saiu, quanto ainda falta reembolsar e quanto fica livre em caixa. Os tres valores sao colunas de
 * statement_summary (saidas, reembolsos pendentes e saldo apos pendencias); a porcentagem e so a razao para o
 * desenho e para o texto. Se as saidas passaram do que havia, a barra mostra so o que saiu e o texto diz quanto faltou.
 */
export function MonthMoney({ summary: s }: { summary: StatementSummary }) {
  const available = s.openingBalanceCents + s.totalInCents;
  const free = s.balanceAfterPendingCents;
  const parts = [
    { key: "out", label: "Saiu", note: "despesas e reembolsos pagos", cents: s.totalOutCents, color: "var(--series-out)" },
    { key: "pending", label: "A reembolsar", note: "ainda não pago", cents: s.pendingReimbursementsCents, color: "var(--warn)" },
    { key: "free", label: "Livre em caixa", note: "o que sobra", cents: Math.max(free, 0), color: "var(--series-base)" },
  ];
  // The bar is as wide as what there was, or as what was committed when that is more (never past 100%).
  const scale = Math.max(available, s.totalOutCents + s.pendingReimbursementsCents, 1);
  const percent = (cents: number) => Math.round((cents / scale) * 100);
  const short = free < 0 ? -free : 0;

  return (
    <section aria-labelledby="month-money-title" className="rounded-[var(--r-lg)] border border-line p-6">
      <h3 id="month-money-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
        <WalletIcon size={20} className="text-ink-2" aria-hidden="true" />
        Para onde foi o dinheiro
      </h3>

      <div className="mt-5">
        <p className="text-foot text-ink-2">Havia no mês</p>
        <p className="mt-1 text-[2.25rem] font-semibold leading-none tracking-[-0.02em] text-brand-800">
          <Amount cents={available} centsClassName="text-[0.5em] font-medium" />
        </p>
        <p className="mt-2 text-foot text-ink-2">
          Saldo inicial {formatBRL(s.openingBalanceCents)} + entradas {formatBRL(s.totalInCents)}
        </p>
      </div>

      <div aria-hidden="true" className="mt-6 flex h-4 gap-0.5 overflow-hidden rounded-full bg-neutral-soft">
        {parts.map((p) => (
          <span key={p.key} data-part={p.key} style={{ width: `${(p.cents / scale) * 100}%`, background: p.color }} className="block h-full" />
        ))}
      </div>

      <ul className="mt-5 space-y-3">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center gap-3">
            <span aria-hidden="true" style={{ background: p.color }} className="size-3 shrink-0 rounded-full" />
            <span className="min-w-0 flex-1 text-sub text-ink">
              {p.label} <span className="text-ink-2">· {p.note}</span>
            </span>
            <span className="shrink-0 text-right text-sub font-semibold tabular-nums text-ink">
              {formatBRL(p.cents)} <span className="font-normal text-ink-2">· {percent(p.cents)}%</span>
            </span>
          </li>
        ))}
      </ul>

      {short > 0 && (
        <p role="note" className="mt-4 rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub font-medium text-warn">
          As saídas passaram do que havia: faltam {formatBRL(short)}.
        </p>
      )}
    </section>
  );
}
