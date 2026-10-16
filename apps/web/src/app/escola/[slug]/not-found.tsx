import type { Metadata } from "next";
import { LinkUnavailableView } from "@/components/ui/LinkUnavailableView";

export const metadata: Metadata = { title: "Página ainda não disponível" };

// Nao diz se a escola existe: a mesma tela vale para um endereco errado e para uma escola que ainda nao abriu o recebimento.
export default function SchoolNotFound() {
  return <LinkUnavailableView />;
}
