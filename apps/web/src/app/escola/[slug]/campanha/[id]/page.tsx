import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CampaignOrderFlow } from "@/components/portal/CampaignOrderFlow";
import { PortalNotice } from "@/components/portal/PortalNotice";
import { PortalShell } from "@/components/portal/PortalShell";
import { getPublicCampaign, getPublicSchool } from "@/lib/api/public";
import { serverFetch } from "@/lib/api/server";
import { isPlausibleSlug } from "@/lib/api/token";
import { formatWait } from "@/lib/auth-messages";

type Props = { params: Promise<{ slug: string; id: string }> };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug, id } = await params;
  if (!isPlausibleSlug(slug) || !UUID.test(id)) return { title: "Campanha não encontrada" };
  const result = await getPublicCampaign(slug, id, { fetchImpl: serverFetch });
  return { title: result.ok ? result.data.title : "Campanha não encontrada" };
}

export default async function CampaignPage({ params }: Props) {
  const { slug, id } = await params;
  if (!isPlausibleSlug(slug) || !UUID.test(id)) notFound();
  // A escola vem do slug da URL e a campanha do id: a API responde o MESMO 404 para uma campanha que nao existe,
  // que ainda e rascunho, que ja acabou, que ainda nao comecou ou que e de outra escola.
  const [school, campaign] = await Promise.all([
    getPublicSchool(slug, { fetchImpl: serverFetch }),
    getPublicCampaign(slug, id, { fetchImpl: serverFetch }),
  ]);
  for (const result of [school, campaign]) {
    if (result.ok) continue;
    if (result.error.status === 404) notFound();
    const limited = result.error.code === "rate_limited";
    return (
      <PortalNotice
        title={limited ? "Muitos acessos agora" : "Não foi possível abrir esta página"}
        text={
          limited
            ? `Aguarde ${formatWait(result.error.retryAfterSeconds)} e tente de novo.`
            : "Não conseguimos falar com o servidor agora. Nada foi cobrado. Tente de novo em instantes."
        }
        reloadHref={`/escola/${slug}/campanha/${id}`}
      />
    );
  }
  if (!school.ok || !campaign.ok) return null; // (ja tratado acima: so para o TypeScript)
  return (
    <PortalShell school={school.data}>
      <CampaignOrderFlow school={school.data} campaign={campaign.data} />
    </PortalShell>
  );
}
