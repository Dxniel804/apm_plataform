import type { Metadata } from "next";
import { PainelPage } from "@/components/painel/PainelPage";

export const metadata: Metadata = { title: "Impostos" };

export default function Page() {
  return <PainelPage area="impostos" />;
}
