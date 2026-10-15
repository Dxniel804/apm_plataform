import { redirect } from "next/navigation";

/**
 * Nao ha tela inicial: a unica porta de entrada e o /login. Quem e responsavel por um aluno entra pelo
 * link (ou QR) que a escola gera, que cai direto na contribuicao ou na campanha; sem o link, escolhe "Contribuir"
 * no /login e informa o codigo da escola.
 */
export default function HomePage() {
  redirect("/login");
}
