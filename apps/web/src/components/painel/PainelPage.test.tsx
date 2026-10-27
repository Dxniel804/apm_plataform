import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { parseSession } from "@/lib/api/auth";
import type { ServerSession } from "@/lib/api/server";
import type { Session } from "@/lib/api/types";
import { SCHOOL_MEMBERSHIP, sessionBody } from "@/test-utils/auth-fixtures";

const auth = vi.hoisted(() => ({ current: { state: "anonymous" } as unknown, environment: null as string | null }));
vi.mock("@/lib/api/server", () => ({ getServerSession: async () => auth.current, getServerEnvironment: async () => auth.environment }));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT:${path}`);
  },
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/components/status/ApiStatusChip", () => ({ ApiStatusChip: () => null }));

import { PainelPage } from "./PainelPage";

async function render(state: ServerSession, area: "resumo" | "despesas" | "solicitacoes" | "campanhas" | "fechamento" | "equipe" = "resumo") {
  auth.current = state;
  const element = await PainelPage({ area });
  return renderToStaticMarkup(element);
}

const withPermissions = (permissions: string[], extra: Record<string, unknown> = {}): ServerSession => ({
  state: "authenticated",
  session: parseSession(
    sessionBody({ active_membership: { ...SCHOOL_MEMBERSHIP, permissions }, ...extra }),
  ) as Session,
});

beforeEach(() => {
  auth.current = { state: "anonymous" };
  auth.environment = null;
  vi.unstubAllEnvs();
});

describe("/painel no servidor", () => {
  it("sem sessao: redireciona para /login e nao renderiza nada do painel", async () => {
    await expect(render({ state: "anonymous" })).rejects.toThrow("NEXT_REDIRECT:/login");
  });

  it("API fora do ar: tela de 'nao foi possivel', SEM redirecionar (nao e logout) e sem dados do painel", async () => {
    const html = await render({ state: "unavailable" });
    expect(html).toContain("Não foi possível abrir o painel");
    expect(html).not.toContain("Movimentações recentes");
  });

  it("com sessao: mostra o nome real da pessoa e o vinculo; os numeros so chegam pela API, no navegador", async () => {
    const session = parseSession(sessionBody()) as Session;
    const html = await render({ state: "authenticated", session });
    expect(html).toContain("Pessoa de Teste");
    expect(html).toContain("Escola Outra");
    expect(html).not.toContain("Protótipo");
    expect(html).not.toMatch(/R\$\s?\d/); // nenhum valor no HTML do servidor
    // nada do CSRF nem de sessao vai para o HTML
    expect(html).not.toContain("csrf-token-que-a-interface-ignora");
  });

  it("funcionário (so despesas) que abre /painel vai para 'Minhas despesas'; quem pode ver a area fica nela", async () => {
    const staff = withPermissions(["expenses:read_own", "expenses:submit"]);
    await expect(render(staff, "resumo")).rejects.toThrow("NEXT_REDIRECT:/painel/despesas");
    await expect(render(staff, "fechamento")).rejects.toThrow("NEXT_REDIRECT:/painel/despesas");
    expect(await render(staff, "despesas")).toContain("Minhas despesas");
    const treasurer = withPermissions(["statement:read", "expenses:approve", "expenses:read_all", "months:close"]);
    expect(await render(treasurer, "despesas")).toContain("Despesas");
    const viewer = withPermissions(["reports:read_aggregate"]);
    await expect(render(viewer, "despesas")).rejects.toThrow("NEXT_REDIRECT:/painel");
  });

  it("campanhas: so a gestao (campaigns:manage) entra; os outros voltam para a sua area", async () => {
    const manager = withPermissions(["statement:read", "campaigns:manage"]);
    expect(await render(manager, "campanhas")).toContain("Campanhas");
    const staff = withPermissions(["expenses:read_own", "expenses:submit"]);
    await expect(render(staff, "campanhas")).rejects.toThrow("NEXT_REDIRECT:/painel/despesas");
    const viewer = withPermissions(["reports:read_aggregate"]);
    await expect(render(viewer, "campanhas")).rejects.toThrow("NEXT_REDIRECT:/painel");
    const onlyCampaigns = withPermissions(["campaigns:manage"]);
    await expect(render(onlyCampaigns, "resumo")).rejects.toThrow("NEXT_REDIRECT:/painel/campanhas");
  });

  it("solicitacoes: o funcionario e a gestao entram; o leitor volta para o resumo; quem so tem solicitacoes cai nelas", async () => {
    const staff = withPermissions(["expenses:read_own", "expenses:submit", "requests:read_own", "requests:submit"]);
    expect(await render(staff, "solicitacoes")).toContain("Minhas solicitações");
    const manager = withPermissions(["statement:read", "requests:read_all", "requests:manage"]);
    expect(await render(manager, "solicitacoes")).toContain("Solicitações");
    const viewer = withPermissions(["reports:read_aggregate"]);
    await expect(render(viewer, "solicitacoes")).rejects.toThrow("NEXT_REDIRECT:/painel");
    const onlyRequests = withPermissions(["requests:read_own", "requests:submit"]);
    await expect(render(onlyRequests, "resumo")).rejects.toThrow("NEXT_REDIRECT:/painel/solicitacoes");
  });
});

describe("Equipe e a Central Forklin (docs/adr-forklin-sso.md, secao 8)", () => {
  const secretaria = () => withPermissions(["statement:read", "invitations:create", "expenses:approve"]);

  it("desligada (padrao): quem pode convidar ve o item Equipe e abre a area", async () => {
    expect(await render(secretaria(), "resumo")).toContain('href="/painel/equipe"');
    expect(await render(secretaria(), "equipe")).toContain("Equipe");
  });

  it("ligada: o item some do menu e /painel/equipe volta para a area da pessoa; o resto do painel segue igual", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    const html = await render(secretaria(), "resumo");
    expect(html).not.toContain("/painel/equipe");
    expect(html).toContain('href="/painel/despesas"');
    await expect(render(secretaria(), "equipe")).rejects.toThrow("NEXT_REDIRECT:/painel");
  });
});

describe("o aviso do ambiente de demonstracao", () => {
  const staff = () => withPermissions(["dashboard:read"]);

  it("em sandbox o painel avisa que e demonstracao", async () => {
    auth.environment = "sandbox";
    expect(await render(staff())).toContain("Você está no ambiente de demonstração.");
  });

  it("em producao, ou sem a informacao da Central, nao mostra aviso", async () => {
    auth.environment = "production";
    expect(await render(staff())).not.toContain("ambiente de demonstração");
    auth.environment = null;
    expect(await render(staff())).not.toContain("ambiente de demonstração");
  });
});
