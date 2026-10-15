import type { Metadata } from "next";
import { PainelPage } from "@/components/painel/PainelPage";

export const metadata: Metadata = { title: "Equipe" };

export default function Page() {
  return <PainelPage area="equipe" />;
}
