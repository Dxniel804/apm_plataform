import { describe, expect, it } from "vitest";
import { areaHref, areasFor, homeArea } from "./permissions";

// Permissoes REAIS de cada papel (docs/auth.md e GET /auth/me).
const STAFF = ["expenses:read_own", "expenses:submit", "requests:read_own", "requests:submit"];
const SECRETARIA = ["campaigns:manage", "contributions:record_cash", "expenses:approve", "expenses:read_all", "invitations:create", "months:close", "months:reopen", "refunds:register", "reimbursements:register", "reports:read", "requests:manage", "reconciliation:manage", "requests:read_all", "school_settings:manage", "statement:read"];
describe("areasFor", () => {
  it("funcionário (staff): so 'Minhas despesas'", () => {
    expect(areasFor(STAFF)).toEqual({ resumo: false, fechamento: false, manageExpenses: false, myExpenses: true, closeMonths: false, reopenMonths: false, requests: true, manageRequests: false, myRequests: true, manageCampaigns: false, manageSettings: false, manageReconciliation: false, manageTeam: false });
    expect(homeArea(areasFor(STAFF))).toBe("despesas");
  });

  it("secretaria: resumo, fila de analise e fechamento; fecha e reabre o mes; nao envia despesa propria", () => {
    expect(areasFor(SECRETARIA)).toEqual({ resumo: true, fechamento: true, manageExpenses: true, myExpenses: false, closeMonths: true, reopenMonths: true, requests: true, manageRequests: true, myRequests: false, manageCampaigns: true, manageSettings: true, manageReconciliation: true, manageTeam: true });
  });

  it("solicitacoes: o funcionario abre as suas e a secretaria recebe e responde", () => {
    expect(areasFor(STAFF)).toMatchObject({ requests: true, myRequests: true, manageRequests: false });
    expect(areasFor(SECRETARIA)).toMatchObject({ requests: true, myRequests: false, manageRequests: true });
    expect(areasFor([])).toMatchObject({ requests: false });
  });

  it("campanhas: so quem tem campaigns:manage, ou seja, a secretaria; o funcionario nao", () => {
    expect(areasFor(SECRETARIA).manageCampaigns).toBe(true);
    expect(areasFor(STAFF).manageCampaigns).toBe(false);
    // quem so tem campanhas cai nelas (nao no resumo, que nao pode ver)
    expect(homeArea(areasFor(["campaigns:manage"]))).toBe("campanhas");
  });

  it("reabrir mes so com months:reopen", () => {
    expect(areasFor(SECRETARIA).reopenMonths).toBe(true);
    expect(areasFor(SECRETARIA.filter((p) => p !== "months:reopen")).reopenMonths).toBe(false);
  });

  it("quem so tem solicitacoes cai nelas (nao no resumo, que nao pode ver)", () => {
    expect(homeArea(areasFor(["requests:submit", "requests:read_own"]))).toBe("solicitacoes");
  });

  it("sem permissao nenhuma nao ve nada e nao inventa area", () => {
    expect(Object.values(areasFor([])).every((v) => v === false)).toBe(true);
  });
});

describe("areaHref", () => {
  it("monta os caminhos com mes e aba validos", () => {
    expect(areaHref("resumo")).toBe("/painel");
    expect(areaHref("despesas")).toBe("/painel/despesas");
    expect(areaHref("despesas", { tab: "minhas" })).toBe("/painel/despesas?aba=minhas");
    expect(areaHref("solicitacoes")).toBe("/painel/solicitacoes");
    expect(areaHref("solicitacoes", { tab: "minhas" })).toBe("/painel/solicitacoes?aba=minhas");
    expect(areaHref("campanhas")).toBe("/painel/campanhas");
    expect(areaHref("fechamento", { period: "2026-09" })).toBe("/painel/fechamento?mes=2026-09");
    expect(areaHref("fechamento", { period: "2026-13" })).toBe("/painel/fechamento");
  });
});
