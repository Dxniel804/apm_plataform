"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import type { CampaignDashboard } from "@/lib/api/types";
import { describeCampaignError } from "@/lib/campaign-labels";
import { saveBlob } from "@/lib/download";
import { formatBRL } from "@/lib/money";

function Card({ label, children, note }: { label: string; children: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-[var(--r-lg)] border border-line p-5">
      <p className="text-sub text-ink-2">{label}</p>
      <p className="mt-1 text-[1.5rem] font-bold leading-tight tabular-nums text-brand-800">{children}</p>
      {note && <p className="mt-1.5 text-foot text-ink-2">{note}</p>}
    </div>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * O resumo de uma campanha: arrecadado, custos, lucro, pedidos por situacao, entregas e o que cada produto vendeu.
 * Tudo calculado no servidor. O lucro so aparece quando TODO produto vendido tem custo; senao, "custo nao informado".
 */
export function CampaignSummaryTab({ schoolId, dashboard }: { schoolId: string; dashboard: CampaignDashboard }) {
  const [downloading, setDownloading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function downloadPdf() {
    if (downloading) return;
    setDownloading(true);
    setProblem(null);
    const result = await api.campaigns.report(schoolId, dashboard.campaignId);
    setDownloading(false);
    if (!result.ok) return setProblem(describeCampaignError(result.error).general ?? "Não foi possível gerar o PDF agora.");
    saveBlob(result.data.blob, `campanha-${dashboard.campaignId.slice(0, 8)}.pdf`);
  }

  const noCost = "custo não informado";
  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card label="Arrecadado" note={plural(dashboard.paidOrdersCount, "pedido aprovado", "pedidos aprovados")}>
          {formatBRL(dashboard.collectedCents)}
        </Card>
        <Card label="Custos" note={dashboard.costComplete ? "Soma do custo de cada unidade vendida." : "Algum produto vendido está sem custo."}>
          {dashboard.costComplete ? formatBRL(dashboard.costCents) : dashboard.costCents > 0 ? `${formatBRL(dashboard.costCents)} informados` : noCost}
        </Card>
        <Card label="Lucro" note="Arrecadado menos os custos.">
          {dashboard.profitCents === null ? <span className="text-[1.0625rem] font-semibold text-ink-2">{noCost}</span> : formatBRL(dashboard.profitCents)}
        </Card>
        <Card label="Unidades vendidas" note="Só de pedidos aprovados.">
          {dashboard.unitsSold}
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card label="Pedidos por pagamento" note={`${plural(dashboard.pendingOrdersCount, "pendente", "pendentes")} · ${plural(dashboard.cancelledOrdersCount, "cancelado", "cancelados")}`}>
          {dashboard.paidOrdersCount + dashboard.pendingOrdersCount + dashboard.cancelledOrdersCount}
        </Card>
        <Card label="Entregas" note={`${plural(dashboard.deliveredOrdersCount, "pedido entregue", "pedidos entregues")} · ${plural(dashboard.toDeliverOrdersCount, "a entregar", "a entregar")}`}>
          {dashboard.deliveredOrdersCount} de {dashboard.paidOrdersCount}
        </Card>
      </div>

      <section aria-labelledby="sold-heading">
        <h3 id="sold-heading" className="text-heading">
          Vendidos por produto
        </h3>
        <div className="mt-3 overflow-x-auto rounded-[var(--r-lg)] border border-line">
          <table className="w-full min-w-[32rem] text-left text-sub">
            <thead className="bg-chip text-ink-2">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Produto</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Vendidos</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Arrecadado</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Custo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {dashboard.items.map((item) => (
                <tr key={item.itemId}>
                  <th scope="row" className="px-4 py-3 font-medium text-ink [overflow-wrap:anywhere]">{item.name}</th>
                  <td className="px-4 py-3 text-right tabular-nums">{item.unitsSold}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatBRL(item.revenueCents)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{item.unitsSold > 0 && !item.costKnown ? "não informado" : formatBRL(item.costCents ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-foot text-ink-2">
          O custo é uma medida de gestão da campanha e não é um lançamento no caixa: a saída de verdade continua sendo a despesa que você registra.
        </p>
      </section>

      <div className="flex flex-wrap items-center gap-4">
        <Button variant="secondary" size="md" onClick={() => void downloadPdf()} disabled={downloading} aria-busy={downloading} className="rounded-full!">
          {downloading ? "Gerando o PDF…" : "Baixar PDF da campanha"}
        </Button>
        <div aria-live="polite">
          {problem && (
            <p role="alert" className="text-sub font-medium text-bad">
              {problem}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
