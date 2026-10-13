"use client";

import { useEffect, useState } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { StatusPill } from "@/components/ui/StatusPill";
import { api } from "@/lib/api";
import type { ApiResult, CampaignStatus, CampaignSummary } from "@/lib/api/types";
import { campaignStatusView, describeCampaignError, describePeriod } from "@/lib/campaign-labels";
import { formatBRL } from "@/lib/money";
import { CampaignDetailPanel } from "./CampaignDetailPanel";
import { CampaignForm } from "./CampaignForm";

const FILTERS: Array<{ status: CampaignStatus | undefined; label: string }> = [
  { status: undefined, label: "Todas" },
  { status: "ACTIVE", label: "À venda" },
  { status: "DRAFT", label: "Rascunhos" },
  { status: "ENDED", label: "Encerradas" },
];

/**
 * Lista das campanhas da escola do vinculo ativo, com "Nova campanha". Cada cartao abre o editor. O filtro e feito
 * aqui (sao poucas campanhas); nada decide estado: a API devolve e a tela mostra.
 */
export function CampaignsBoard({ schoolId }: { schoolId: string }) {
  const [filter, setFilter] = useState<CampaignStatus | undefined>(undefined);
  const [version, setVersion] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const key = `${schoolId}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<CampaignSummary[]> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.campaigns.list(schoolId).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, key]);

  const res = loaded?.key === key ? loaded.res : loaded?.res ?? null;
  const all = res && res.ok ? res.data : [];
  const items = filter ? all.filter((campaign) => campaign.status === filter) : all;
  const reload = () => setVersion((n) => n + 1);

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-4">
        <div role="group" aria-label="Filtrar por situação" className="flex min-w-0 flex-1 basis-72 flex-wrap gap-2.5">
          {FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              aria-pressed={filter === f.status}
              onClick={() => {
                setFilter(f.status);
                setOpenId(null);
                setBanner(null);
              }}
              className={chipClass(filter === f.status)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <Button variant="chip" size="md" onClick={() => setCreating(true)} className="min-h-12 w-full px-7 sm:w-auto">
          Nova campanha
        </Button>
      </div>

      <CampaignForm
        schoolId={schoolId}
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(id) => {
          setCreating(false);
          setFilter(undefined);
          setBanner("Campanha criada como rascunho. Adicione os produtos e ponha à venda quando estiver pronta.");
          setOpenId(id);
          reload();
        }}
      />

      {banner && (
        <p role="status" className="mb-4 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">
          {banner}
        </p>
      )}

      {!res && (
        <div role="status" aria-busy="true" aria-live="polite">
          <span className="sr-only">Carregando as campanhas…</span>
          <div aria-hidden="true" className="rounded-[var(--r-lg)] border border-line p-6">
            <div className="skeleton h-4 w-48" />
            <div className="skeleton mt-4 h-10 w-full" />
          </div>
        </div>
      )}
      {res && !res.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {res.error.status === 403 ? "O seu perfil não mexe nas campanhas desta escola." : describeCampaignError(res.error).general}
        </p>
      )}

      {res && res.ok && items.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-12 text-center">
          <h2 className="text-heading">{all.length === 0 ? "Nenhuma campanha ainda" : "Nenhuma campanha nesta situação"}</h2>
          <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">
            {all.length === 0
              ? "Crie uma campanha para vender produtos às famílias: uma festa, um kit, uma rifa. Elas escolhem as quantidades e pagam pelo Pix."
              : "Quando houver campanhas nesta situação, elas aparecem aqui."}
          </p>
        </div>
      )}

      {items.length > 0 && (
        <ul aria-label="Campanhas da escola" className="space-y-4">
          {items.map((campaign) => {
            const view = campaignStatusView(campaign.status);
            const isOpen = openId === campaign.id;
            const period = describePeriod(campaign.startsOn, campaign.endsOn);
            return (
              <li key={campaign.id} className="overflow-hidden rounded-[var(--r-lg)] border border-line bg-white">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-5 sm:px-8 sm:py-6">
                  <div className="min-w-0 flex-1 basis-56">
                    <p className="text-[1.0625rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere] sm:text-[1.25rem]">{campaign.title}</p>
                    <p className="mt-1 text-sub text-ink-2">
                      {campaign.activeItemsCount} {campaign.activeItemsCount === 1 ? "produto à venda" : "produtos à venda"}
                      {period ? ` · ${period}` : ""}
                      {campaign.paidOrdersCount > 0 ? ` · ${campaign.paidOrdersCount} ${campaign.paidOrdersCount === 1 ? "pedido pago" : "pedidos pagos"} (${formatBRL(campaign.paidCents)})` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                    <StatusPill tone={view.tone}>{view.label}</StatusPill>
                  </div>
                  <Button variant="chip" size="md" aria-expanded={isOpen} aria-label={`${isOpen ? "Fechar" : "Abrir"} a campanha ${campaign.title}`} onClick={() => setOpenId(isOpen ? null : campaign.id)} className="min-h-12 w-full px-8 sm:w-auto">
                    {isOpen ? "Fechar" : "Abrir"}
                  </Button>
                </div>
                {isOpen && (
                  <CampaignDetailPanel
                    schoolId={schoolId}
                    campaignId={campaign.id}
                    onChanged={(message) => {
                      if (message) setBanner(message);
                      reload();
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
