"use client";

import type { CampaignTab } from "@/lib/painel-section";
import { areasFor } from "@/lib/permissions";
import { CampaignPage } from "./CampaignPage";
import { CampaignsBoard } from "./CampaignsBoard";

interface Props {
  schoolId: string;
  permissions: string[];
  /** A campanha aberta (/painel/campanhas/{id}); sem ela, a lista. */
  campaignId?: string;
  tab?: CampaignTab;
}

/**
 * Area "Campanhas": as campanhas que a gestao vende as familias (festa, kit, rifa), com produtos e preco. So
 * quem tem `campaigns:manage` ve; a API confere de novo a cada pedido.
 */
export function CampaignsArea({ schoolId, permissions, campaignId, tab = "resumo" }: Props) {
  const areas = areasFor(permissions);
  if (!areas.manageCampaigns) {
    return (
      <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
        O seu perfil não mexe nas campanhas desta escola.
      </p>
    );
  }
  if (campaignId) return <CampaignPage key={campaignId} schoolId={schoolId} campaignId={campaignId} initialTab={tab} />;
  return (
    <div>
      {/* O Figma repete o titulo da pagina dentro do painel; para leitor de tela ele ja e o h1 do cabecalho. */}
      <p aria-hidden="true" className="mb-2 text-[clamp(1.5rem,1.2rem+1vw,2.25rem)] font-semibold leading-tight text-brand-800">
        Campanhas
      </p>
      <p className="mb-6 max-w-[62ch] text-body text-ink-2">
        Venda produtos às famílias: uma festa, um kit, uma rifa. Elas escolhem as quantidades na página da escola e pagam pelo Pix.
      </p>
      <CampaignsBoard schoolId={schoolId} />
    </div>
  );
}
