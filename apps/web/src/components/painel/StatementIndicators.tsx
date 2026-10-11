import Image from "next/image";
import type { ReactNode } from "react";
import { Amount } from "@/components/ui/Amount";
import { CashCoinIcon, Cart4Icon, ClockHistoryIcon, ListCheckIcon } from "@/components/ui/icons";
import type { StatementSummary } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { periodLabel } from "@/lib/statement-labels";
import { BalanceChart } from "./BalanceChart";
import { OutflowSplit } from "./OutflowSplit";

function Stat({ icon, label, value, note }: { icon: ReactNode; label: string; value: ReactNode; note: string }) {
  return (
    <div className="px-5 py-5 sm:px-8 sm:py-7">
      <dt className="flex items-center gap-3 text-[1.0625rem] font-light text-ink sm:text-[1.25rem] lg:text-[1.375rem]">
        <span aria-hidden="true" className="text-ink-2">
          {icon}
        </span>
        {label}
      </dt>
      <dd className="mt-1.5 text-kpi text-brand-800 sm:pl-9">{value}</dd>
      <dd className="mt-0.5 text-foot text-ink-2 sm:pl-9">{note}</dd>
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
 * Resumo do mes (Figma "Gestao"). Todos os valores sao colunas de statement_summary: nada e somado aqui. Os
 * DOIS saldos aparecem com nome proprio: "em caixa" (principal) e "apos reembolsos pendentes" (secundario).
 */
export function StatementIndicators({ summary }: { summary: StatementSummary }) {
  return (
    <div className="space-y-6 lg:space-y-8">
      <section aria-labelledby="indicators-title" className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] xl:items-center">
        <div className="flex items-center justify-between gap-3">
          {/* @container: o numero escala com a largura do bloco (cqw), entao nunca estoura a 320px. */}
          <div className="@container min-w-0 flex-1">
            <h2 id="indicators-title" className="text-[1.0625rem] font-normal text-ink-2 sm:text-[1.25rem] lg:text-[1.375rem]">
              Seu saldo em caixa em {periodLabel(summary.period)}
            </h2>
            <p className="mt-2 text-[min(4rem,15cqw)] font-bold leading-none tracking-[-0.03em] text-brand-800">
              <Amount cents={summary.closingBalanceCents} />
            </p>
          </div>
          <Image
            src="/brand/3d-coin.webp"
            alt=""
            width={360}
            height={408}
            sizes="(min-width: 1280px) 9rem, 6rem"
            className="h-24 w-auto shrink-0 sm:h-32 xl:h-40"
          />
        </div>

        {/* Saldo secundario: a "lampada" do Figma pendurada na borda de cima do cartao. */}
        <div className="relative min-h-36 rounded-[var(--r-lg)] border border-line px-6 py-5 pr-28 sm:px-8 sm:pr-40">
          <p className="text-sub text-ink-2">Após reembolsos pendentes</p>
          <p className="mt-1 text-kpi text-brand-800">
            <Amount cents={summary.balanceAfterPendingCents} />
          </p>
          <Image
            src="/brand/3d-lamp.webp"
            alt=""
            width={400}
            height={630}
            sizes="10rem"
            className="absolute right-5 top-0 h-[88%] w-auto sm:right-10"
          />
        </div>
      </section>

      <dl className="grid grid-cols-1 divide-y divide-line overflow-hidden rounded-[var(--r-lg)] border border-line sm:grid-cols-2 sm:divide-y-0 sm:[&>div:nth-child(n+3)]:border-t sm:[&>div:nth-child(even)]:border-l sm:[&>div]:border-line">
        <Stat
          icon={<ClockHistoryIcon size={24} />}
          label="Saldo inicial"
          value={<Amount cents={summary.openingBalanceCents} symbolClassName="text-brand-800" />}
          note="Caixa na virada do mês anterior"
        />
        <Stat
          icon={<CashCoinIcon size={24} />}
          label="Entradas"
          value={<Amount cents={summary.totalInCents} symbolClassName="text-brand-800" />}
          note={entriesNote(summary)}
        />
        <Stat
          icon={<Cart4Icon size={24} />}
          label="Saídas pagas"
          value={<Amount cents={summary.totalOutCents} symbolClassName="text-brand-800" />}
          note={`Despesas ${formatBRL(summary.expensesOutCents)} · reembolsos ${formatBRL(summary.reimbursementsOutCents)}`}
        />
        <Stat
          icon={<ListCheckIcon size={24} />}
          label="Lançamentos"
          value={String(summary.entriesCount)}
          note={summary.entriesCount === 1 ? "lançamento no mês" : "lançamentos no mês"}
        />
      </dl>

      <div className="grid gap-5 lg:grid-cols-2 lg:gap-6">
        <BalanceChart summary={summary} />
        <OutflowSplit summary={summary} />
      </div>
    </div>
  );
}
