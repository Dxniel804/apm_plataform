import type { MovementKind } from "./status";

/** Secoes do painel: o resumo e uma lista por tipo do dominio (4 tipos DISTINTOS). */
export type PainelSection = "resumo" | MovementKind;

const SLUG_TO_KIND: Record<string, MovementKind> = {
  contribuicoes: "CONTRIBUTION",
  despesas: "EXPENSE",
  reembolsos: "REIMBURSEMENT",
  devolucoes: "REFUND",
};

export const KIND_TO_SLUG: Record<MovementKind, string> = {
  CONTRIBUTION: "contribuicoes",
  EXPENSE: "despesas",
  REIMBURSEMENT: "reembolsos",
  REFUND: "devolucoes",
};

export function parseSection(raw: string | string[] | undefined): PainelSection {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value !== undefined && Object.hasOwn(SLUG_TO_KIND, value) ? SLUG_TO_KIND[value]! : "resumo";
}

const PERIOD = /^\d{4}-(0[1-9]|1[0-2])$/;

/** `?mes=YYYY-MM` da URL; qualquer outra coisa vira "sem mes" (a API usa o mes corrente da escola). */
export function parsePeriod(raw: string | string[] | undefined): string | undefined {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value !== undefined && PERIOD.test(value) ? value : undefined;
}

export function sectionHref(section: PainelSection, period?: string): string {
  const params: string[] = [];
  if (section !== "resumo") params.push(`tipo=${KIND_TO_SLUG[section]}`);
  if (period && PERIOD.test(period)) params.push(`mes=${period}`);
  return params.length > 0 ? `/painel?${params.join("&")}` : "/painel";
}

/** As abas da pagina de uma campanha (`?aba=`): o resumo, os pedidos e os produtos (o editor). */
export type CampaignTab = "resumo" | "pedidos" | "produtos";
export const CAMPAIGN_TABS: readonly CampaignTab[] = ["resumo", "pedidos", "produtos"];

export function parseCampaignTab(raw: string | string[] | undefined): CampaignTab {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return CAMPAIGN_TABS.find((tab) => tab === value) ?? "resumo";
}
