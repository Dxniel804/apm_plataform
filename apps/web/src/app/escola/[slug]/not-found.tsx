import type { Metadata } from "next";
import { NotFoundView } from "@/components/ui/NotFoundView";

export const metadata: Metadata = { title: "Página ainda não disponível" };

// Nao diz se a escola existe: o mesmo aviso vale para um endereco errado e para uma escola que ainda nao abriu o recebimento.
export default function SchoolNotFound() {
  return (
    <NotFoundView
      friendly
      title="Esta página ainda não está disponível"
      text="Este link ainda não está aberto para contribuições. Se a gestão da APM enviou este endereço, ele pode abrir em breve: tente de novo em alguns dias ou confirme o endereço com a gestão."
    />
  );
}
