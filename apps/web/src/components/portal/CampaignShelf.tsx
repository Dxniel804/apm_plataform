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
    <section aria-labelledby="campaigns-heading" className="mb-10">
      <h2 id="campaigns-heading" className="text-headline text-brand-800">
        Campanhas da escola
      </h2>
      <p className="mt-1 text-body text-ink-2">Escolha os produtos, veja o total e pague pelo Pix.</p>
      <ul className="mt-5 grid gap-4 sm:grid-cols-2">
        {campaigns.map((campaign) => {
          const period = describePeriod(null, campaign.endsOn);
          return (
            <li key={campaign.id} className="overflow-hidden rounded-[var(--r-lg)] border border-line bg-white">
              <Link
                href={`/escola/${encodeURIComponent(slug)}/campanha/${encodeURIComponent(campaign.id)}`}
                className="block h-full outline-offset-2 hover:bg-info-soft/40"
              >
                {campaign.hasCover ? (
                  // eslint-disable-next-line @next/next/no-img-element -- imagem publica da API (mesma origem), com tamanho e cache proprios
                  <img src={campaignCoverUrl(slug, campaign.id, campaign.coverVersion)} alt="" loading="lazy" className="aspect-[16/9] w-full object-cover" />
                ) : (
                  <span aria-hidden="true" className="grid aspect-[16/9] w-full place-items-center bg-info-soft text-brand-800">
                    <ImageIcon size={32} />
                  </span>
                )}
                <span className="block space-y-1.5 p-5">
                  <span className="block text-[1.25rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere]">{campaign.title}</span>
                  {campaign.description && <span className="line-clamp-2 block text-sub text-ink-2 [overflow-wrap:anywhere]">{campaign.description}</span>}
                  <span className="block text-foot text-ink-3">
                    {campaign.itemsCount} {campaign.itemsCount === 1 ? "produto" : "produtos"}
                    {period ? ` · ${period}` : ""}
                  </span>
                  <span className="mt-2 inline-flex min-h-11 items-center rounded-full bg-grad-chip px-6 text-sub font-bold text-white">Ver produtos</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
