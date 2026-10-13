import { describe, expect, it } from "vitest";
import { areaHref, areasFor, homeArea } from "./permissions";

// Permissoes REAIS de cada papel (docs/auth.md e GET /auth/me).
const STAFF = ["expenses:read_own", "expenses:submit", "requests:read_own", "requests:submit"];
const TREASURER = ["contributions:record_cash", "expenses:approve", "expenses:read_all", "months:close", "refunds:register", "reimbursements:register", "reports:read", "requests:manage", "requests:read_all", "statement:read"];
const SCHOOL_ADMIN = [...TREASURER, "expenses:read_own", "expenses:submit", "invitations:create", "memberships:manage", "months:reopen", "organization:update", "reports:read_aggregate", "requests:read_own", "requests:submit", "school:update"];
const VIEWER = ["reports:read_aggregate"];

describe("areasFor", () => {
  it("funcionário (staff): so 'Minhas despesas'", () => {
    expect(areasFor(STAFF)).toEqual({ resumo: false, fechamento: false, manageExpenses: false, myExpenses: true, closeMonths: false, reopenMonths: false, requests: true, manageRequests: false, myRequests: true });
    expect(homeArea(areasFor(STAFF))).toBe("despesas");
  });

  it("gestão (treasurer): resumo, fila de analise e fechamento; fecha mes mas nao reabre; nao envia despesa propria", () => {
    expect(areasFor(TREASURER)).toEqual({ resumo: true, fechamento: true, manageExpenses: true, myExpenses: false, closeMonths: true, reopenMonths: false, requests: true, manageRequests: true, myRequests: false });
  });

  it("administrador da escola (school_admin): tudo, inclusive reabrir mes; envia e analisa", () => {
    expect(areasFor(SCHOOL_ADMIN)).toMatchObject({ resumo: true, fechamento: true, manageExpenses: true, myExpenses: true, closeMonths: true, reopenMonths: true });
  });

  it("solicitacoes: o funcionario abre as suas, a gestao recebe e responde, o administrador faz as duas coisas, o leitor nao ve", () => {
    expect(areasFor(STAFF)).toMatchObject({ requests: true, myRequests: true, manageRequests: false });
    expect(areasFor(TREASURER)).toMatchObject({ requests: true, myRequests: false, manageRequests: true });
    expect(areasFor(SCHOOL_ADMIN)).toMatchObject({ requests: true, myRequests: true, manageRequests: true });
    expect(areasFor(VIEWER)).toMatchObject({ requests: false, myRequests: false, manageRequests: false });
    expect(areasFor([])).toMatchObject({ requests: false });
  });

  it("reabrir mes so com months:reopen (ADR-020: so o administrador da escola)", () => {
    expect(areasFor(SCHOOL_ADMIN.filter((p) => p !== "months:reopen")).reopenMonths).toBe(false);
    expect(areasFor(TREASURER).reopenMonths).toBe(false);
  });

  it("viewer: resumo e fechamento so de leitura, sem despesas e sem fechar", () => {
    expect(areasFor(VIEWER)).toEqual({ resumo: true, fechamento: true, manageExpenses: false, myExpenses: false, closeMonths: false, reopenMonths: false, requests: false, manageRequests: false, myRequests: false });
    expect(homeArea(areasFor(VIEWER))).toBe("resumo");
    // quem so tem solicitacoes cai nelas (nao no resumo, que nao pode ver)
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
    expect(areaHref("fechamento", { period: "2026-09" })).toBe("/painel/fechamento?mes=2026-09");
    expect(areaHref("fechamento", { period: "2026-13" })).toBe("/painel/fechamento");
  });
});
