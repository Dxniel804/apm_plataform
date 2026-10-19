/**
 * O que cada area do painel pede. As permissoes vem de `active_membership.permissions` (GET /auth/me e
 * POST /auth/context): o cliente nao inventa nenhuma. Serve so para mostrar ou esconder; o servidor
 * confere de novo a cada pedido e continua sendo a autoridade (403, 404, 409 e 422 tem texto proprio).
 */
export interface Areas {
  /** Resumo, lancamentos e pendencias (statement:read) ou so os totais (reports:read_aggregate). */
  resumo: boolean;
  /** Fechamento mensal: leitura. */
  fechamento: boolean;
  /** Fila de analise da gestao: aprovar, recusar, pedir correcao, reembolsar e pagar. */
  manageExpenses: boolean;
  /** "Minhas despesas": quem pode enviar despesas. */
  myExpenses: boolean;
  closeMonths: boolean;
  reopenMonths: boolean;
  /** "Solicitacoes": quem abre pedidos ou le os pedidos (a gestao le todos e responde). */
  requests: boolean;
  /** Caixa de entrada da gestao: ler todos os pedidos e responder. */
  manageRequests: boolean;
  /** "Minhas solicitacoes": quem pode abrir pedidos. */
  myRequests: boolean;
  /** "Personalizacao": as campanhas (produtos e carrinho) que a gestao vende as familias. */
  manageCampaigns: boolean;
  /** "Configuracoes": os valores sugeridos, as metas e o link publico da escola (school_settings:manage). */
  manageSettings: boolean;
  /** "Conciliacao": as contas bancarias e a comparacao do extrato com o caixa (reconciliation:manage). */
  manageReconciliation: boolean;
  /** "Equipe": quem traz os funcionarios para a escola (invitations:create). */
  manageTeam: boolean;
}

export function areasFor(permissions: readonly string[]): Areas {
  const has = (p: string) => permissions.includes(p);
  const aggregate = has("statement:read") || has("reports:read_aggregate");
  return {
    resumo: aggregate,
    fechamento: aggregate,
    manageExpenses: has("expenses:approve") || has("reimbursements:register") || has("expenses:read_all"),
    myExpenses: has("expenses:submit"),
    closeMonths: has("months:close"),
    reopenMonths: has("months:reopen"),
    requests: has("requests:submit") || has("requests:read_own") || has("requests:read_all"),
    manageRequests: has("requests:read_all") || has("requests:manage"),
    myRequests: has("requests:submit"),
    manageCampaigns: has("campaigns:manage"),
    manageSettings: has("school_settings:manage"),
    manageReconciliation: has("reconciliation:manage"),
    manageTeam: has("invitations:create"),
  };
}

export type PainelArea = "resumo" | "despesas" | "solicitacoes" | "campanhas" | "conciliacao" | "pdde" | "equipe" | "configuracoes" | "fechamento" | "conta";

export function areaHref(area: PainelArea, params: { period?: string; tab?: "minhas" } = {}): string {
  const base = area === "resumo" ? "/painel" : `/painel/${area}`;
  const query: string[] = [];
  if (params.tab) query.push(`aba=${params.tab}`);
  if (params.period && /^\d{4}-(0[1-9]|1[0-2])$/.test(params.period)) query.push(`mes=${params.period}`);
  return query.length > 0 ? `${base}?${query.join("&")}` : base;
}

/** Para onde mandar quem abre /painel sem poder ver o resumo (ex.: funcionario): a sua area. */
export function homeArea(areas: Areas): PainelArea {
  if (areas.resumo) return "resumo";
  if (areas.myExpenses || areas.manageExpenses) return "despesas";
  if (areas.requests) return "solicitacoes";
  if (areas.manageCampaigns) return "campanhas";
  return "resumo";
}
