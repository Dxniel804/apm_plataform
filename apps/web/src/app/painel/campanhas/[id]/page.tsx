import type { Metadata } from "next";
import { PainelPage } from "@/components/painel/PainelPage";

export const metadata: Metadata = { title: "Campanha" };

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ aba?: string | string[] }> };

export default async function Page({ params, searchParams }: Props) {
  const { id } = await params;
  const { aba } = await searchParams;
  return <PainelPage area="campanhas" campaignId={id} aba={aba} />;
}
