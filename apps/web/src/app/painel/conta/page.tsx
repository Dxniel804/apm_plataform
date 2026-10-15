import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Alterar senha" };

/** O endereco antigo continua valendo: a troca de senha mora em Configuracoes. */
export default function Page(): never {
  redirect("/painel/configuracoes#senha");
}
