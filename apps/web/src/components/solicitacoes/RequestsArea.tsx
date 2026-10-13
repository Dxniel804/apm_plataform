"use client";

import Link from "next/link";
import { chipClass } from "@/components/ui/Button";
import { areaHref, areasFor } from "@/lib/permissions";
import { RequestsBoard } from "./RequestsBoard";

interface Props {
  schoolId: string;
  userId: string;
  permissions: string[];
  /** `?aba=minhas`: quem tem as duas funcoes (diretor) escolhe entre a caixa de entrada e as proprias solicitacoes. */
  tab: "minhas" | "fila";
}

/**
 * Area "Solicitacoes". Funcionario: so "Minhas solicitacoes". Gestao: so a caixa de entrada. Quem tem as duas
 * funcoes (diretor): abas. As permissoes vem da sessao; a API confere de novo.
 */
export function RequestsArea({ schoolId, userId, permissions, tab }: Props) {
  const areas = areasFor(permissions);
  if (!areas.requests) {
    return (
      <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
        O seu perfil não tem acesso às solicitações desta escola.
      </p>
    );
  }
  const both = areas.manageRequests && areas.myRequests;
  const scope = both ? (tab === "minhas" ? "mine" : "inbox") : areas.manageRequests ? "inbox" : "mine";
  return (
    <div>
      {/* O Figma repete o titulo da pagina dentro do painel; para leitor de tela ele ja e o h1 do cabecalho. */}
      <p aria-hidden="true" className="mb-6 text-[clamp(1.5rem,1.2rem+1vw,2.25rem)] font-semibold leading-tight text-brand-800">
        {scope === "mine" ? "Minhas solicitações" : "Solicitações"}
      </p>
      {both && (
        <nav aria-label="Solicitações" className="mb-6 flex flex-wrap gap-2.5">
          {([["fila", "Caixa de entrada", areaHref("solicitacoes")], ["minhas", "Minhas solicitações", areaHref("solicitacoes", { tab: "minhas" })]] as const).map(([id, label, href]) => (
            <Link key={id} href={href} aria-current={(tab === "minhas" ? "minhas" : "fila") === id ? "page" : undefined} className={chipClass((tab === "minhas" ? "minhas" : "fila") === id)}>
              {label}
            </Link>
          ))}
        </nav>
      )}
      <RequestsBoard key={scope} schoolId={schoolId} userId={userId} permissions={permissions} scope={scope} />
    </div>
  );
}
