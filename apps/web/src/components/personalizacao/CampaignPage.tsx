"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusPill } from "@/components/ui/StatusPill";
import { api } from "@/lib/api";
import type { ApiResult, CampaignDashboard } from "@/lib/api/types";
import { campaignStatusView, describeCampaignError } from "@/lib/campaign-labels";
import { CAMPAIGN_TABS, type CampaignTab } from "@/lib/painel-section";
import { CampaignDetailPanel } from "./CampaignDetailPanel";
import { CampaignOrders } from "./CampaignOrders";
import { CampaignSummaryTab } from "./CampaignSummaryTab";

const TAB_LABELS: Record<CampaignTab, string> = { resumo: "Resumo", pedidos: "Pedidos", produtos: "Produtos" };

interface Props {
  schoolId: string;
  campaignId: string;
  initialTab: CampaignTab;
}

/**
 * A pagina de uma campanha (/painel/campanhas/{id}): Resumo (o que entrou, o que custou, o que cada produto vendeu),
 * Pedidos (quem comprou, o pagamento e a entrega) e Produtos (o editor). Os numeros vem todos da API.
 */
export function CampaignPage({ schoolId, campaignId, initialTab }: Props) {
  const [tab, setTab] = useState<CampaignTab>(initialTab);
  const [version, setVersion] = useState(0);
  const key = `${schoolId}|${campaignId}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<CampaignDashboard> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.campaigns.dashboard(schoolId, campaignId).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, campaignId, key]);

  // Fica com o ultimo resultado enquanto recarrega (a tela nao pisca).
  const res = loaded?.res ?? null;
  const reload = () => setVersion((n) => n + 1);

  function choose(next: CampaignTab) {
    setTab(next);
    // O endereco acompanha a aba (para copiar e voltar), sem recarregar a pagina.
    window.history.replaceState(null, "", `/painel/campanhas/${encodeURIComponent(campaignId)}?aba=${next}`);
  }

  const dashboard = res && res.ok ? res.data : null;
  const view = dashboard ? campaignStatusView(dashboard.status) : null;

  return (
    <div>
      <Link href="/painel/campanhas" className="mb-3 inline-flex min-h-11 items-center gap-1.5 text-sub font-medium text-brand-800 underline-offset-4 hover:underline">
        <span aria-hidden="true">←</span> Todas as campanhas
      </Link>

      {!res && (
        <div role="status" aria-busy="true" aria-live="polite">
          <span className="sr-only">Carregando a campanha…</span>
          <div aria-hidden="true" className="skeleton h-8 w-64" />
        </div>
      )}
      {res && !res.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {res.error.status === 404 ? "Não encontramos esta campanha." : (describeCampaignError(res.error).general ?? "Não foi possível abrir a campanha.")}
        </p>
      )}

      {dashboard && view && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2">
            <h2 className="min-w-0 text-[clamp(1.375rem,1.1rem+1vw,2rem)] font-semibold leading-tight text-brand-800 [overflow-wrap:anywhere]">{dashboard.title}</h2>
            <StatusPill tone={view.tone}>{view.label}</StatusPill>
          </div>

          <div role="tablist" aria-label="Partes da campanha" className="mb-6 flex gap-1 overflow-x-auto rounded-2xl bg-chip p-1">
            {CAMPAIGN_TABS.map((id) => (
              <button
                key={id}
                type="button"
                role="tab"
                id={`campaign-tab-${id}`}
                aria-selected={tab === id}
                aria-controls="campaign-panel"
                onClick={() => choose(id)}
                className={`flex min-h-11 flex-1 items-center justify-center whitespace-nowrap rounded-xl border px-4 text-[0.9375rem] transition-colors ${
                  tab === id ? "border-pill-line bg-white font-semibold text-brand-800" : "border-transparent font-medium text-ink-2 hover:bg-white/60"
                }`}
              >
                {TAB_LABELS[id]}
              </button>
            ))}
          </div>

          <div id="campaign-panel" role="tabpanel" aria-labelledby={`campaign-tab-${tab}`}>
            {tab === "resumo" && <CampaignSummaryTab schoolId={schoolId} dashboard={dashboard} />}
            {tab === "pedidos" && <CampaignOrders schoolId={schoolId} campaignId={campaignId} onChanged={reload} />}
            {tab === "produtos" && (
              <div className="-mx-5 sm:-mx-6">
                <CampaignDetailPanel schoolId={schoolId} campaignId={campaignId} onChanged={reload} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
