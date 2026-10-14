import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ContributionFlow } from "@/components/portal/ContributionFlow";
import { PortalNotice } from "@/components/portal/PortalNotice";
import { PortalShell } from "@/components/portal/PortalShell";
import { getPublicCampaigns, getPublicSchool } from "@/lib/api/public";
import { serverFetch } from "@/lib/api/server";
import { isPlausibleSlug } from "@/lib/api/token";
import { formatWait } from "@/lib/auth-messages";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  if (!isPlausibleSlug(slug)) return { title: "Escola não encontrada" };
  const result = await getPublicSchool(slug, { fetchImpl: serverFetch });
  if (!result.ok) return { title: "Escola não encontrada" };
  // A previa quando o link e compartilhado (WhatsApp, Instagram): o nome da escola, uma frase e a imagem desta pasta.
  const title = `Contribuir · ${result.data.name}`;
  const description = `Contribua com a ${result.data.apmName} pelo Pix. O dinheiro vai direto para a conta da APM.`;
  return {
    metadataBase: new URL(process.env.PUBLIC_BASE_URL ?? "http://localhost:3000"),
    title,
    description,
    openGraph: { title, description, type: "website", locale: "pt_BR", siteName: "APM Digital" },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function SchoolPortalPage({ params }: Props) {
  const { slug } = await params;
  if (!isPlausibleSlug(slug)) notFound();
  // A escola vem do slug da URL, nunca de parametro do cliente (ADR-010). A API responde o mesmo 404
  // para qualquer slug que nao exista.
  const result = await getPublicSchool(slug, { fetchImpl: serverFetch });
  if (!result.ok) {
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
        reloadHref={`/escola/${slug}`}
      />
    );
  }
  // As campanhas a venda sao um extra: se a consulta falhar, a pagina da contribuicao segue como sempre.
  const campaigns = await getPublicCampaigns(slug, { fetchImpl: serverFetch });
  return (
    <PortalShell school={result.data}>
      <ContributionFlow school={result.data} campaigns={campaigns.ok ? campaigns.data : []} />
    </PortalShell>
  );
}
