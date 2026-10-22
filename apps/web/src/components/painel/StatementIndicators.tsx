import { Amount } from "@/components/ui/Amount";
import { ArrowDownIcon, ArrowUpIcon, WalletIcon } from "@/components/ui/icons";
import type { StatementSummary } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { periodLabel } from "@/lib/statement-labels";
import { KpiCards } from "./KpiCards";

/**
 * Os tres numeros do mes que a gestao le primeiro: quanto ha em caixa, quanto entrou e quanto saiu. Todos sao colunas
 * de statement_summary (nada e somado aqui). O saldo "apos reembolsos pendentes" so aparece quando ha reembolso a
 * pagar, como nota do saldo em caixa; saldo inicial, tipos de entrada e contagem de lancamentos ficam nas telas
 * de cada lancamento, nao aqui.
 */
export function StatementIndicators({ summary: s }: { summary: StatementSummary }) {
  return (
    <div className="space-y-4">
      <KpiCards
        label={`Números de ${periodLabel(s.period)}`}
        items={[
          {
            key: "balance",
            icon: <WalletIcon size={20} />,
            label: "Saldo em caixa",
            value: <Amount cents={s.closingBalanceCents} centsClassName="text-[0.5em] font-medium" />,
            note:
              s.pendingReimbursementsCents > 0 ? (
                <p>
                  <span className="font-semibold text-brand-800">{formatBRL(s.balanceAfterPendingCents)}</span> livres após reembolsos
                </p>
              ) : undefined,
          },
          { key: "in", icon: <ArrowDownIcon size={20} />, label: "Entradas", value: <Amount cents={s.totalInCents} centsClassName="text-[0.5em] font-medium" /> },
          { key: "out", icon: <ArrowUpIcon size={20} />, label: "Saídas", value: <Amount cents={s.totalOutCents} centsClassName="text-[0.5em] font-medium" /> },
        ]}
      />

      {s.gatewayFeesCents > 0 && (
        <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-brand-800">
          Tarifas do gateway: <strong className="font-semibold">{formatBRL(s.gatewayFeesCents)}</strong>. O banco recebe esse valor a menos.
        </p>
      )}
    </div>
  );
}
