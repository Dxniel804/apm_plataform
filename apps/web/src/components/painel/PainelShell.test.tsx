import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseSession } from "@/lib/api/auth";
import type { ApiError, ApiResult, Session } from "@/lib/api/types";
import { ADMIN_MEMBERSHIP, SCHOOL_MEMBERSHIP, sessionBody } from "@/test-utils/auth-fixtures";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/components/status/ApiStatusChip", () => ({ ApiStatusChip: () => null }));
vi.mock("@/components/despesas/ExpensesArea", () => ({ ExpensesArea: () => <div data-testid="expenses-area" /> }));
vi.mock("./PainelData", () => ({
  PainelData: (p: { schoolId: string; section: string; period?: string; permissions: string[] }) => (
    <div data-testid="data">{`${p.schoolId}|${p.section}|${p.period ?? ""}|${p.permissions.join(",")}`}</div>
  ),
}));

import { PainelShell } from "./PainelShell";

const session = (overrides: Record<string, unknown> = {}) => parseSession(sessionBody(overrides)) as Session;
const problem = (code: string, status: number): ApiResult<never> => ({
  ok: false,
  error: { kind: "problem", status, code } as ApiError,
});

function renderShell(s: Session = session(), props: { area?: "resumo" | "despesas" | "fechamento"; period?: string } = {}) {
  return render(<PainelShell session={s} area={props.area ?? "resumo"} period={props.period} />);
}

beforeEach(() => {
  router.replace.mockReset();
  router.refresh.mockReset();
});
afterEach(() => vi.restoreAllMocks());

describe("PainelShell com sessao real", () => {
  it("mostra o nome, o papel e a escola reais; todo vinculo e de UMA escola e o painel e dela", () => {
    renderShell();
    expect(screen.getAllByText("Pessoa de Teste").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Administrador da escola").length).toBeGreaterThan(0);
    const switcher = screen.getAllByRole("button", { name: /Escola Outra/ })[0]!;
    expect(switcher).toHaveTextContent("Administrador da escola");
    expect(screen.getByTestId("data")).toHaveTextContent(ADMIN_MEMBERSHIP.school.id);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByText(/Protótipo/)).not.toBeInTheDocument();
  });

  it("vinculo de escola: o titulo e a escola real e os numeros vem da escola DO VINCULO ATIVO (id da sessao)", () => {
    const s = session({ active_membership: { ...SCHOOL_MEMBERSHIP, permissions: ["statement:read", "reports:read"] } });
    renderShell(s, { period: "2026-09" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Dashboard");
    expect(screen.getAllByText(/Escola Teste/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("data")).toHaveTextContent(`${SCHOOL_MEMBERSHIP.school.id}|resumo|2026-09|statement:read,reports:read`);
  });

  it("o menu muda por perfil, a partir das permissoes da sessao", () => {
    const names = () => screen.getAllByRole("link").map((l) => l.textContent);
    const staff = session({ active_membership: { ...SCHOOL_MEMBERSHIP, role: "staff", permissions: ["expenses:read_own", "expenses:submit"] } });
    const { unmount } = renderShell(staff, { area: "despesas" });
    expect(screen.getAllByRole("link", { name: "Minhas despesas" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Fechamento" })).not.toBeInTheDocument();
    unmount();

    const treasurer = session({ active_membership: { ...SCHOOL_MEMBERSHIP, permissions: ["statement:read", "expenses:approve", "expenses:read_all", "months:close"] } });
    const t = renderShell(treasurer);
    expect(names()).toEqual(expect.arrayContaining(["Dashboard", "Despesas", "Fechamento"]));
    expect(screen.queryByRole("link", { name: "Minhas despesas" })).not.toBeInTheDocument();
    t.unmount();

    const viewer = session({ active_membership: { ...SCHOOL_MEMBERSHIP, role: "viewer", permissions: ["reports:read_aggregate"] } });
    renderShell(viewer);
    expect(names()).toEqual(expect.arrayContaining(["Dashboard", "Fechamento"]));
    expect(screen.queryByRole("link", { name: "Despesas" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Contribuições" })).not.toBeInTheDocument();
  });

  it("os links do menu carregam o mes escolhido (resumo e fechamento)", () => {
    renderShell(session({ active_membership: { ...SCHOOL_MEMBERSHIP, permissions: ["statement:read", "expenses:read_all"] } }), { period: "2026-09" });
    expect(screen.getAllByRole("link", { name: "Dashboard" })[0]).toHaveAttribute("href", "/painel?mes=2026-09");
    expect(screen.getAllByRole("link", { name: "Fechamento" })[0]).toHaveAttribute("href", "/painel/fechamento?mes=2026-09");
    // "Despesas" existe duas vezes: o tipo de lancamento (dentro de "Lancamento do mes") e a area de despesas.
    const expenseHrefs = screen.getAllByRole("link", { name: "Despesas" }).map((l) => l.getAttribute("href"));
    expect(expenseHrefs).toEqual(["/painel?tipo=despesas&mes=2026-09", "/painel/despesas"]);
    expect(screen.getByRole("link", { name: "Contribuições" })).toHaveAttribute("href", "/painel?tipo=contribuicoes&mes=2026-09");
  });

  it("o seletor lista os vinculos reais (uma escola cada) e troca de contexto pelo id do vinculo", async () => {
    const switchContext = vi.spyOn(api.auth, "switchContext").mockResolvedValue({ ok: true, data: session() });
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /Escola Outra/ })[0]!);
    const list = screen.getByRole("list", { name: "Escolas da sua conta" });
    expect(within(list).getByRole("button", { name: /Escola Outra/ })).toHaveAttribute("aria-current", "true");
    await user.click(within(list).getByRole("button", { name: /Escola Teste/ }));

    expect(switchContext).toHaveBeenCalledTimes(1);
    expect(switchContext).toHaveBeenCalledWith(SCHOOL_MEMBERSHIP.membership_id);
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
  });

  it("trocar para o vinculo que ja esta ativo nao chama a API", async () => {
    const switchContext = vi.spyOn(api.auth, "switchContext");
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /Escola Outra/ })[0]!);
    await user.click(within(screen.getByRole("list", { name: "Escolas da sua conta" })).getByRole("button", { name: /Escola Outra/ }));
    expect(switchContext).not.toHaveBeenCalled();
  });

  it("context_not_allowed: mostra o texto em portugues e NAO recarrega", async () => {
    vi.spyOn(api.auth, "switchContext").mockResolvedValue(problem("context_not_allowed", 403));
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /Escola Outra/ })[0]!);
    await user.click(screen.getByRole("button", { name: /Escola Teste/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Você não tem acesso a esse vínculo");
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("sessao perdida ao trocar: volta para /login", async () => {
    vi.spyOn(api.auth, "switchContext").mockResolvedValue(problem("session_revoked", 401));
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /Escola Outra/ })[0]!);
    await user.click(screen.getByRole("button", { name: /Escola Teste/ }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
  });

  it("Sair chama POST /auth/logout e vai para /login", async () => {
    const logout = vi.spyOn(api.auth, "logout").mockResolvedValue({ ok: true, data: true });
    renderShell();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Sair" })[0]!);
    expect(logout).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
  });

  it("Sair que falha (csrf, rede) avisa e fica na pagina: a sessao pode continuar viva", async () => {
    vi.spyOn(api.auth, "logout").mockResolvedValue(problem("csrf_failed", 403));
    renderShell();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Sair" })[0]!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Recarregue a página");
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: "Sair" })[0]).toBeEnabled();
  });
});

describe("sessao sem vinculo ativo (varios vinculos, nenhum escolhido)", () => {
  it("mostra a escolha e nenhum dado do painel; escolher chama POST /auth/context", async () => {
    const switchContext = vi.spyOn(api.auth, "switchContext").mockResolvedValue({ ok: true, data: session() });
    renderShell(session({ active_membership: null }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Onde você vai atuar?");
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByText("Movimentações recentes")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: /Escola Teste/ }));
    expect(switchContext).toHaveBeenCalledWith(SCHOOL_MEMBERSHIP.membership_id);
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
  });

  it("conta sem nenhum vinculo ativo: aviso claro e so a opcao de sair", () => {
    renderShell(session({ active_membership: null, memberships: [] }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sem vínculo ativo");
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sair" })).toBeInTheDocument();
  });

  it("os dois vinculos aparecem com o papel de cada um", () => {
    renderShell(session({ active_membership: null }));
    expect(screen.getByRole("button", { name: /Escola Outra/ })).toHaveTextContent("Administrador da escola");
    expect(screen.getByRole("button", { name: /Escola Teste/ })).toHaveTextContent("Tesouraria");
  });
});

describe("menu (Figma Gestao)", () => {
  const treasurer = () =>
    session({ active_membership: { ...SCHOOL_MEMBERSHIP, permissions: ["statement:read", "expenses:approve", "expenses:read_all", "months:close"] } });

  it("o grupo 'Lançamento do mês' abre e fecha e lista os 4 tipos de lançamento", async () => {
    renderShell(treasurer());
    const group = screen.getByRole("button", { name: "Lançamento do mês" });
    expect(group).toHaveAttribute("aria-expanded", "true"); // o dashboard abre o grupo
    expect(screen.getByRole("link", { name: "Reembolsos" })).toHaveAttribute("href", "/painel?tipo=reembolsos");
    expect(screen.getByRole("link", { name: "Devoluções" })).toHaveAttribute("href", "/painel?tipo=devolucoes");
    await userEvent.setup().click(group);
    expect(group).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "Reembolsos" })).not.toBeInTheDocument();
  });

  it("a pagina atual e marcada com aria-current (Dashboard no resumo; o tipo dentro de um lancamento)", () => {
    const { unmount } = render(<PainelShell session={treasurer()} area="resumo" section="resumo" />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    unmount();
    render(<PainelShell session={treasurer()} area="resumo" section="REIMBURSEMENT" />);
    expect(screen.getByRole("link", { name: "Reembolsos" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Reembolsos");
  });

  it("no celular o menu abre numa gaveta modal (nome acessivel, Esc fecha, escolher uma pagina fecha)", async () => {
    renderShell(treasurer());
    const user = userEvent.setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrir o menu" }));
    const drawer = screen.getByRole("dialog", { name: "Menu do painel" });
    expect(within(drawer).getByRole("link", { name: "Fechamento" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Sair" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Abrir o menu" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Fechamento" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("recolher o menu vira uma coluna de icones, sem perder nome acessivel, e a escolha fica lembrada", async () => {
    window.localStorage.removeItem("apm.sidebar.collapsed");
    const { unmount } = renderShell(treasurer());
    const user = userEvent.setup();
    const toggle = screen.getByRole("button", { name: "Recolher o menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Expandir o menu" })).toHaveAttribute("aria-expanded", "false");
    // recolhido, os links continuam com nome (so o texto fica fora da tela)
    expect(screen.getByRole("link", { name: "Fechamento" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contribuições" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lançamento do mês" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("apm.sidebar.collapsed")).toBe("1");
    unmount();
    renderShell(treasurer());
    expect(screen.getByRole("button", { name: "Expandir o menu" })).toBeInTheDocument();
    window.localStorage.removeItem("apm.sidebar.collapsed");
  });
});
