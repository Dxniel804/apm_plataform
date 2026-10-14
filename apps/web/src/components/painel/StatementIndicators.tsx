import type { ReactNode } from "react";
import { Amount } from "@/components/ui/Amount";
import { ArrowDownIcon, ArrowUpIcon, BankIcon, ClockIcon, ListIcon, TrendDownIcon, WalletIcon } from "@/components/ui/icons";
import type { StatementSummary } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { periodLabel } from "@/lib/statement-labels";
import { BalanceChart } from "./BalanceChart";
import { OutflowSplit } from "./OutflowSplit";

function Stat({ icon, label, value, note }: { icon: ReactNode; label: string; value: ReactNode; note: string }) {
  return (
    <div className="px-6 py-5 sm:py-6">
      <dt className="flex items-center gap-2.5 text-[1rem] text-ink">
        <span aria-hidden="true" className="text-ink-2">
          {icon}
        </span>
        {label}
      </dt>
      <dd className="mt-3 text-kpi text-brand-800">{value}</dd>
      <dd className="mt-1 text-foot text-ink-2">{note}</dd>
    </div>
  );
}

/** Como as entradas se dividem: sempre as contribuicoes; "outras" e "devolucoes recebidas" so quando houver. */
function entriesNote(s: StatementSummary): string {
  const parts = [`Contribuições ${formatBRL(s.contributionsInCents)}`];
  if (s.otherInCents > 0) parts.push(`outras ${formatBRL(s.otherInCents)}`);
  if (s.refundsInCents > 0) parts.push(`devoluções recebidas ${formatBRL(s.refundsInCents)}`);
  return parts.join(" · ");
}

/**
 * Resumo do mes (visual Paper v2). Todos os valores sao colunas de statement_summary: nada e somado aqui. Os
 * DOIS saldos aparecem com nome proprio: "em caixa" (principal) e "apos reembolsos pendentes" (secundario).
 * `pendings` (a gestao) entra ao lado da composicao das saidas.
 */
export function StatementIndicators({ summary, pendings }: { summary: StatementSummary; pendings?: ReactNode }) {
  return (
    <div className="space-y-5 lg:space-y-6">
      <section aria-labelledby="indicators-title" className="grid gap-6 lg:grid-cols-2 lg:gap-0">
        <div className="flex items-center justify-between gap-4 lg:pr-8">
          {/* @container: o numero escala com a largura do bloco (cqw), entao nunca estoura a 320px. */}
          <div className="@container min-w-0 flex-1">
            <h2 id="indicators-title" className="text-[1rem] font-normal text-ink">
              Seu saldo em caixa em {periodLabel(summary.period)}
            </h2>
            <p className="mt-3 text-[min(3.25rem,13cqw)] font-semibold leading-none tracking-[-0.02em] text-brand-800">
              <Amount cents={summary.closingBalanceCents} centsClassName="text-[0.42em] font-medium" />
            </p>
          </div>
          <span aria-hidden="true" className="hidden size-24 shrink-0 place-items-center rounded-[1.75rem] bg-info-soft text-brand-600 sm:grid">
            <WalletIcon size={40} strokeWidth={1.6} />
          </span>
        </div>

        <div className="flex items-center justify-between gap-4 border-t border-line pt-6 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
          <div className="@container min-w-0 flex-1">
            <p className="text-[1rem] text-ink">Após reembolsos pendentes</p>
            <p className="mt-3 text-[min(3.25rem,13cqw)] font-semibold leading-none tracking-[-0.02em] text-brand-800">
              <Amount cents={summary.balanceAfterPendingCents} centsClassName="text-[0.42em] font-medium" />
            </p>
            {summary.pendingReimbursementsCents > 0 && (
              <p className="mt-3 flex items-center gap-1.5 text-foot font-medium text-warn">
                <TrendDownIcon size={14} />
                {formatBRL(-summary.pendingReimbursementsCents)} a reembolsar
              </p>
            )}
          </div>
          <span aria-hidden="true" className="hidden size-24 shrink-0 place-items-center rounded-[1.75rem] bg-info-soft text-brand-600 sm:grid">
            <ClockIcon size={40} strokeWidth={1.6} />
          </span>
        </div>
      </section>

      <dl className="grid grid-cols-1 divide-y divide-line overflow-hidden rounded-[var(--r-lg)] border border-line sm:grid-cols-2 sm:divide-y-0 sm:[&>div:nth-child(n+3)]:border-t sm:[&>div:nth-child(even)]:border-l sm:[&>div]:border-line xl:grid-cols-4 xl:[&>div:nth-child(n+2)]:border-l xl:[&>div:nth-child(n+3)]:border-t-0">
        <Stat
          icon={<BankIcon size={20} />}
          label="Saldo inicial"
          value={<Amount cents={summary.openingBalanceCents} centsClassName="text-[0.5em] font-medium" />}
          note="Caixa na virada do mês anterior"
        />
        <Stat
          icon={<ArrowDownIcon size={20} />}
          label="Entradas"
          value={<Amount cents={summary.totalInCents} centsClassName="text-[0.5em] font-medium" />}
          note={entriesNote(summary)}
        />
        <Stat
          icon={<ArrowUpIcon size={20} />}
          label="Total de saídas"
          value={<Amount cents={summary.totalOutCents} centsClassName="text-[0.5em] font-medium" />}
          note={`Despesas ${formatBRL(summary.expensesOutCents)} · reembolsos ${formatBRL(summary.reimbursementsOutCents)}`}
        />
        <Stat
          icon={<ListIcon size={20} />}
          label="Lançamentos"
          value={String(summary.entriesCount)}
          note={summary.entriesCount === 1 ? "lançamento no mês" : "lançamentos no mês"}
        />
      </dl>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <BalanceChart summary={summary} />
        <OutflowSplit summary={summary} />
      </div>
      {pendings}
    </div>
  );
}
