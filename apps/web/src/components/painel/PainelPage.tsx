import { redirect } from "next/navigation";
import { PainelShell } from "@/components/painel/PainelShell";
import { SessionUnavailable } from "@/components/painel/SessionUnavailable";
import { getServerSession } from "@/lib/api/server";
import { parseCampaignTab, parsePeriod, parseSection } from "@/lib/painel-section";
import { areaHref, areasFor, homeArea, type PainelArea } from "@/lib/permissions";

interface Props {
  area: PainelArea;
  tipo?: string | string[];
  mes?: string | string[];
  aba?: string | string[];
  /** A campanha aberta (/painel/campanhas/{id}); sem ela a area mostra a lista. */
  campaignId?: string;
}

/**
 * Pagina de servidor de todas as areas do painel: exige sessao (sem ela volta para o login), manda quem nao
 * pode ver a area para a sua (funcionario: Minhas despesas) e entrega ao cliente so a sessao. Os numeros vem da
 * API, no navegador, para a escola do vinculo ativo.
 */
export async function PainelPage({ area, tipo, mes, aba, campaignId }: Props) {
  const auth = await getServerSession();
  if (auth.state === "anonymous") redirect("/login");
  if (auth.state === "unavailable") return <SessionUnavailable />;

  const active = auth.session.activeMembership;
  if (active) {
    const areas = areasFor(active.permissions);
    const allowed =
      area === "conta" ||
      (area === "resumo"
        ? areas.resumo
        : area === "fechamento"
          ? areas.fechamento
          : area === "solicitacoes"
            ? areas.requests
            : area === "campanhas"
              ? areas.manageCampaigns
              : area === "configuracoes"
                ? areas.manageSettings
                : area === "conciliacao"
                  ? areas.manageReconciliation
                  : areas.manageExpenses || areas.myExpenses);
    const home = homeArea(areas);
    if (!allowed && home !== area) redirect(areaHref(home));
  }

  const tab = (Array.isArray(aba) ? aba[0] : aba) === "minhas" ? "minhas" : "fila";
  const campaignTab = parseCampaignTab(Array.isArray(aba) ? aba[0] : aba);
  return (
    <PainelShell session={auth.session} area={area} section={parseSection(tipo)} tab={tab} period={parsePeriod(mes)} campaignId={campaignId} campaignTab={campaignTab} />
  );
}
