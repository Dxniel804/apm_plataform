import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiResult, Page, StaffRequestSummary } from "@/lib/api/types";
import { REQUEST_AUTHOR_ID, REQUEST_MANAGER_ID, requestDetail, requestSummary } from "@/test-utils/request-fixtures";
import { SCHOOL_ID, page } from "@/test-utils/statement-fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }) }));

import { RequestsArea } from "./RequestsArea";
import { RequestsBoard } from "./RequestsBoard";

const ok = (items: StaffRequestSummary[], next: string | null = null): ApiResult<Page<StaffRequestSummary>> => ({ ok: true, data: page(items, next) });
const STAFF = ["requests:read_own", "requests:submit"];
const MANAGER = ["requests:read_all", "requests:manage"];
const ADMIN = [...STAFF, ...MANAGER];

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(api.requests, "download").mockResolvedValue({ ok: true, data: { blob: new Blob(["x"]), contentType: "image/jpeg" } as never });
});
afterEach(() => vi.restoreAllMocks());

describe("Minhas solicitacoes (funcionario)", () => {
  it("lista as proprias com a situacao em portugues; o detalhe so abre sob demanda", async () => {
    const list = vi.spyOn(api.requests, "list").mockResolvedValue(
      ok([
        requestSummary({ id: "r1", title: "Pedido aberto", status: "OPEN" }),
        requestSummary({ id: "r2", title: "Pedido andando", status: "IN_PROGRESS", category: "MAINTENANCE", attachmentsCount: 2 }),
        requestSummary({ id: "r3", title: "Pedido pronto", status: "RESOLVED" }),
        requestSummary({ id: "r4", title: "Pedido desfeito", status: "CANCELLED", attachmentsCount: 0 }),
      ]),
    );
    const get = vi.spyOn(api.requests, "get").mockResolvedValue({ ok: true, data: requestDetail({ id: "r2", status: "IN_PROGRESS", description: "Detalhe do pedido" }) });
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={STAFF} scope="mine" />);

    const items = await screen.findByRole("list", { name: "Minhas solicitações" });
    expect(list).toHaveBeenCalledWith(SCHOOL_ID, { status: undefined, category: undefined, limit: 50 });
    for (const label of ["Aberta", "Em andamento", "Resolvida", "Cancelada"]) expect(within(items).getByText(label)).toBeInTheDocument();
    expect(within(items).getByText(/Manutenção · .* · 2 fotos/)).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();

    await userEvent.setup().click(screen.getByRole("button", { name: "Abrir detalhes da solicitação Pedido andando" }));
    expect(await screen.findByText("Detalhe do pedido")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(SCHOOL_ID, "r2");
  });

  it("vazio, 403 e 'Nova solicitacao' abre a janela", async () => {
    vi.spyOn(api.requests, "list").mockResolvedValue(ok([]));
    const { unmount } = render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={STAFF} scope="mine" />);
    expect(await screen.findByRole("heading", { name: "Você ainda não abriu solicitações" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Nova solicitação" }));
    expect(screen.getByRole("dialog", { name: "Nova solicitação" })).toBeInTheDocument();
    unmount();

    vi.spyOn(api.requests, "list").mockResolvedValue({ ok: false, error: { kind: "problem", status: 403, code: "permission_denied" } });
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={STAFF} scope="mine" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("O seu perfil não vê as solicitações");
  });

  it("quem le a escola toda (administrador) ve em 'minhas' so as proprias", async () => {
    vi.spyOn(api.requests, "list").mockResolvedValue(ok([requestSummary({ id: "m", title: "Minha", authorUserId: REQUEST_AUTHOR_ID }), requestSummary({ id: "o", title: "De outra pessoa", authorUserId: REQUEST_MANAGER_ID })]));
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={ADMIN} scope="mine" />);

    expect(await screen.findByText("Minha")).toBeInTheDocument();
    expect(screen.queryByText("De outra pessoa")).not.toBeInTheDocument();
  });

  it("depois de abrir um pedido a lista recarrega e mostra o aviso", async () => {
    const list = vi.spyOn(api.requests, "list").mockResolvedValue(ok([]));
    vi.spyOn(api.requests, "create").mockResolvedValue({ ok: true, data: requestDetail({ id: "novo" }) });
    vi.spyOn(api.requests, "get").mockResolvedValue({ ok: true, data: requestDetail({ id: "novo" }) });
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={STAFF} scope="mine" />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Nova solicitação" }));
    await user.selectOptions(screen.getByLabelText("Categoria"), "EVENT");
    await user.type(screen.getByLabelText("Título"), "Festa");
    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Solicitação enviada para a gestão.");
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });
});

describe("Caixa de entrada da gestao", () => {
  it("comeca em 'Abertas' (filtro na API), troca de situacao e de categoria", async () => {
    const list = vi.spyOn(api.requests, "list").mockResolvedValue(ok([requestSummary({ title: "Pedido de alguem", authorUserId: REQUEST_AUTHOR_ID })]));
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_MANAGER_ID} permissions={MANAGER} scope="inbox" />);
    const user = userEvent.setup();

    expect(await screen.findByText("Pedido de alguem")).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith(SCHOOL_ID, { status: "OPEN", category: undefined, limit: 50 });
    expect(screen.getByRole("button", { name: "Abertas" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Nova solicitação" })).not.toBeInTheDocument(); // a gestao nao abre pedidos

    await user.click(screen.getByRole("button", { name: "Resolvidas" }));
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(SCHOOL_ID, { status: "RESOLVED", category: undefined, limit: 50 }));
    await user.click(screen.getByRole("button", { name: "Todas" }));
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(SCHOOL_ID, { status: undefined, category: undefined, limit: 50 }));
    await user.selectOptions(screen.getByLabelText("Categoria"), "FINANCE");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(SCHOOL_ID, { status: undefined, category: "FINANCE", limit: 50 }));
  });

  it("carregar mais acrescenta a proxima pagina; erro da pagina nao apaga o que ja esta na tela", async () => {
    const list = vi
      .spyOn(api.requests, "list")
      .mockResolvedValueOnce(ok([requestSummary({ id: "a", title: "Primeiro" })], "cursor-2"))
      .mockResolvedValueOnce({ ok: false, error: { kind: "network" } as never })
      .mockResolvedValueOnce(ok([requestSummary({ id: "b", title: "Segundo" })]));
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_MANAGER_ID} permissions={MANAGER} scope="inbox" />);
    const user = userEvent.setup();

    await screen.findByText("Primeiro");
    await user.click(screen.getByRole("button", { name: "Carregar mais" }));
    expect(await screen.findByText(/Nada foi alterado/)).toBeInTheDocument();
    expect(screen.getByText("Primeiro")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Carregar mais" }));

    expect(await screen.findByText("Segundo")).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith(SCHOOL_ID, { status: "OPEN", category: undefined, limit: 50, cursor: "cursor-2" });
    expect(screen.queryByRole("button", { name: "Carregar mais" })).not.toBeInTheDocument();
  });

  it("marca como 'sua' o pedido que a propria pessoa abriu", async () => {
    vi.spyOn(api.requests, "list").mockResolvedValue(ok([requestSummary({ title: "Meu pedido", authorUserId: REQUEST_MANAGER_ID })]));
    render(<RequestsBoard schoolId={SCHOOL_ID} userId={REQUEST_MANAGER_ID} permissions={ADMIN} scope="inbox" />);

    expect(await screen.findByText(/· sua/)).toBeInTheDocument();
  });
});

describe("area Solicitacoes", () => {
  it("funcionario ve so 'Minhas solicitacoes'; gestao so a caixa de entrada; sem permissao, aviso", async () => {
    vi.spyOn(api.requests, "list").mockResolvedValue(ok([]));
    const { unmount } = render(<RequestsArea schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={STAFF} tab="fila" />);
    expect(await screen.findByRole("heading", { name: "Você ainda não abriu solicitações" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Solicitações" })).not.toBeInTheDocument();
    unmount();

    const second = render(<RequestsArea schoolId={SCHOOL_ID} userId={REQUEST_MANAGER_ID} permissions={MANAGER} tab="minhas" />);
    expect(await screen.findByRole("heading", { name: "Nenhuma solicitação nesta situação" })).toBeInTheDocument();
    second.unmount();

    render(<RequestsArea schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={["reports:read"]} tab="fila" />);
    expect(screen.getByRole("note")).toHaveTextContent("não tem acesso às solicitações");
  });

  it("administrador escolhe entre a caixa de entrada e as proprias (?aba=minhas)", async () => {
    vi.spyOn(api.requests, "list").mockResolvedValue(ok([]));
    const { unmount } = render(<RequestsArea schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={ADMIN} tab="fila" />);
    const nav = await screen.findByRole("navigation", { name: "Solicitações" });
    expect(within(nav).getByRole("link", { name: "Caixa de entrada" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Minhas solicitações" })).toHaveAttribute("href", "/painel/solicitacoes?aba=minhas");
    unmount();

    render(<RequestsArea schoolId={SCHOOL_ID} userId={REQUEST_AUTHOR_ID} permissions={ADMIN} tab="minhas" />);
    expect(await screen.findByRole("button", { name: "Nova solicitação" })).toBeInTheDocument();
  });
});
