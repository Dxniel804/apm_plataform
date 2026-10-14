import Link from "next/link";
import { ImageIcon } from "@/components/ui/icons";
import { campaignCoverUrl } from "@/lib/api/public";
import type { PublicCampaignSummary } from "@/lib/api/types";
import { describePeriod } from "@/lib/campaign-labels";

/**
 * As campanhas a venda na escola (festa, kit, rifa), no alto da pagina publica: cada cartao leva a pagina da
 * campanha, onde a familia escolhe os produtos. So aparece quando a API devolveu alguma. A capa e publica (so
 * as de campanhas a venda); sem capa, o espaco vazio.
 */
export function CampaignShelf({ slug, campaigns }: { slug: string; campaigns: PublicCampaignSummary[] }) {
  if (campaigns.length === 0) return null;
  return (
    <section aria-labelledby="campaigns-heading">
      <h2 id="campaigns-heading" className="text-[1.4375rem] font-bold leading-tight tracking-[-0.015em] text-brand-800">
        Campanhas da escola
      </h2>
      <p className="mt-1 text-sub text-ink-2">Escolha os produtos, veja o total e pague pelo Pix.</p>
      <ul className="mt-5 grid gap-4 sm:grid-cols-2">
        {campaigns.map((campaign) => {
          const period = describePeriod(null, campaign.endsOn);
          return (
            <li key={campaign.id} className="overflow-hidden rounded-[1.25rem] border border-line bg-white">
              <Link
                href={`/escola/${encodeURIComponent(slug)}/campanha/${encodeURIComponent(campaign.id)}`}
                className="block h-full outline-offset-2 hover:bg-info-soft/40"
              >
                {campaign.hasCover ? (
                  // eslint-disable-next-line @next/next/no-img-element -- imagem publica da API (mesma origem), com tamanho e cache proprios
                  <img src={campaignCoverUrl(slug, campaign.id, campaign.coverVersion)} alt="" loading="lazy" className="aspect-[16/9] w-full object-cover" />
                ) : (
                  <span aria-hidden="true" className="grid h-24 w-full place-items-center bg-info-soft text-brand-600">
                    <span className="grid size-[3.75rem] place-items-center rounded-full bg-white">
                      <ImageIcon size={28} />
                    </span>
                  </span>
                )}
                <span className="block space-y-1 p-4">
                  <span className="block text-[1.125rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere]">{campaign.title}</span>
                  {campaign.description && <span className="line-clamp-2 block text-sub text-ink-2 [overflow-wrap:anywhere]">{campaign.description}</span>}
                  <span className="block text-foot text-ink-3">
                    {campaign.itemsCount} {campaign.itemsCount === 1 ? "produto" : "produtos"}
                    {period ? ` · ${period}` : ""}
                  </span>
                  <span className="mt-3 flex min-h-[2.875rem] items-center justify-center gap-2 rounded-[var(--r-ctl)] bg-brand-800 px-6 text-[0.9375rem] font-semibold text-white">Ver produtos</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
