import type { CampaignDetail } from "@/lib/api/types";
import { describePeriod } from "@/lib/campaign-labels";
import { formatBRL } from "@/lib/money";
import { CampaignImage } from "./CampaignImage";

/**
 * "Como a familia ve": a pagina da campanha no tamanho do celular, com o que esta escrito agora. So leitura:
 * mostra os produtos que estao ligados, com o preco de hoje. O carrinho de verdade esta na pagina publica.
 */
export function CampaignPreview({ schoolId, campaign }: { schoolId: string; campaign: CampaignDetail }) {
  const items = campaign.items.filter((item) => item.isActive);
  const period = describePeriod(campaign.startsOn, campaign.endsOn);
  return (
    <div role="group" aria-label="Pré-visualização da página da campanha" className="mx-auto w-full max-w-[22rem] overflow-hidden rounded-[1.5rem] border-[6px] border-ink bg-white shadow-sm">
      <CampaignImage
        schoolId={schoolId}
        campaignId={campaign.id}
        present={campaign.hasCover}
        version={campaign.coverVersion}
        alt="Capa da campanha"
        className="aspect-[16/9] w-full"
      />
      <div className="space-y-3 p-4">
        <p className="text-[1.25rem] font-semibold leading-tight text-brand-800 [overflow-wrap:anywhere]">{campaign.title}</p>
        {period && <p className="text-foot text-ink-3">À venda {period}</p>}
        {campaign.description && <p className="whitespace-pre-line text-sub text-ink-2 [overflow-wrap:anywhere]">{campaign.description}</p>}
        {items.length === 0 ? (
          <p className="rounded-[var(--r-md)] bg-info-soft px-3 py-2 text-foot text-info">Nenhum produto à venda ainda.</p>
        ) : (
          <ul aria-label="Produtos" className="divide-y divide-line">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 py-3">
                <CampaignImage
                  schoolId={schoolId}
                  campaignId={campaign.id}
                  itemId={item.id}
                  present={item.hasImage}
                  version={item.imageVersion}
                  alt={`Imagem de ${item.name}`}
                  className="size-14 shrink-0 rounded-[0.75rem]"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sub font-semibold text-ink [overflow-wrap:anywhere]">{item.name}</p>
                  <p className="text-foot text-ink-2">{formatBRL(item.priceCents)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
