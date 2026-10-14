import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push }) }));
import { api } from "@/lib/api";
import type { ApiResult, CampaignSummary } from "@/lib/api/types";
import { CAMPAIGN_ID, detail, summary } from "@/test-utils/campaign-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { CampaignsArea } from "./CampaignsArea";
import { CampaignsBoard } from "./CampaignsBoard";

const ok = (items: CampaignSummary[]): ApiResult<CampaignSummary[]> => ({ ok: true, data: items });
const MANAGER = ["campaigns:manage", "statement:read"];

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
  push.mockClear();
});
afterEach(() => vi.restoreAllMocks());

describe("area Campanhas", () => {
  it("so quem tem campaigns:manage ve as campanhas; os outros recebem um aviso e nenhuma chamada a API", () => {
    const list = vi.spyOn(api.campaigns, "list");
    render(<CampaignsArea schoolId={SCHOOL_ID} permissions={["requests:read_all", "expenses:read_all"]} />);
    expect(screen.getByRole("note")).toHaveTextContent("não mexe nas campanhas");
    expect(list).not.toHaveBeenCalled();
  });

  it("a gestao ve o titulo, o texto de ajuda e a lista da escola", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([summary({ title: "Festa Junina" })]));
    render(<CampaignsArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    expect(await screen.findByRole("list", { name: "Campanhas da escola" })).toBeInTheDocument();
    expect(screen.getByText(/Elas escolhem as quantidades/)).toBeInTheDocument();
  });
});

describe("lista de campanhas", () => {
  it("mostra a situacao em portugues, os produtos, o periodo e o que os pedidos pagos trouxeram", async () => {
    const list = vi.spyOn(api.campaigns, "list").mockResolvedValue(
      ok([
        summary({ id: "c1", title: "Festa Junina", status: "ACTIVE", activeItemsCount: 3, endsOn: "2026-06-30", paidOrdersCount: 2, paidCents: 5400 }),
        summary({ id: "c2", title: "Kit escolar", status: "DRAFT", activeItemsCount: 1 }),
        summary({ id: "c3", title: "Rifa do ano passado", status: "ENDED", activeItemsCount: 0 }),
      ]),
    );
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);

    const items = await within(await screen.findByRole("list", { name: "Campanhas da escola" })).findAllByRole("listitem");
    expect(list).toHaveBeenCalledWith(SCHOOL_ID);
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Festa Junina");
    expect(items[0]).toHaveTextContent("À venda");
    expect(items[0]).toHaveTextContent("3 produtos à venda");
    expect(items[0]).toHaveTextContent("até 30 de jun");
    expect(items[0]).toHaveTextContent("2 pedidos pagos");
    expect(items[0]).toHaveTextContent("R$ 54,00");
    expect(items[1]).toHaveTextContent("Rascunho");
    expect(items[1]).toHaveTextContent("1 produto à venda");
    expect(items[2]).toHaveTextContent("Encerrada");
  });

  it("filtra por situacao sem chamar a API de novo", async () => {
    const list = vi.spyOn(api.campaigns, "list").mockResolvedValue(
      ok([summary({ id: "c1", title: "No ar", status: "ACTIVE" }), summary({ id: "c2", title: "Rascunho A", status: "DRAFT" })]),
    );
    const user = userEvent.setup();
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    await screen.findByRole("list", { name: "Campanhas da escola" });

    await user.click(screen.getByRole("button", { name: "Rascunhos" }));
    expect(screen.queryByText("No ar")).not.toBeInTheDocument();
    expect(screen.getByText("Rascunho A")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Encerradas" }));
    expect(screen.getByRole("heading", { name: "Nenhuma campanha nesta situação" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("sem campanhas: explica o que fazer", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([]));
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    expect(await screen.findByRole("heading", { name: "Nenhuma campanha ainda" })).toBeInTheDocument();
    expect(screen.getByText(/pagam pelo Pix/)).toBeInTheDocument();
  });

  it("403 e erro de rede viram texto em portugues, sem quebrar a tela", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValueOnce({ ok: false, error: { kind: "problem", status: 403, code: "permission_denied" } });
    const { unmount } = render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("não mexe nas campanhas");
    unmount();
    vi.spyOn(api.campaigns, "list").mockResolvedValueOnce({ ok: false, error: { kind: "network" } });
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nada foi alterado");
  });

  it("cada campanha leva a pagina dela (/painel/campanhas/{id})", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([summary()]));
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);

    const link = await screen.findByRole("link", { name: "Abrir a campanha Festa Junina" });
    expect(link).toHaveAttribute("href", `/painel/campanhas/${CAMPAIGN_ID}`);
  });
});

describe("nova campanha", () => {
  it("pede o titulo antes de falar com a API", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([]));
    const create = vi.spyOn(api.campaigns, "create");
    const user = userEvent.setup();
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    await screen.findByRole("heading", { name: "Nenhuma campanha ainda" });

    await user.click(screen.getByRole("button", { name: "Nova campanha" }));
    await user.click(screen.getByRole("button", { name: "Criar rascunho" }));

    expect(screen.getByText("Escreva o título da campanha.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("recusa data de fim antes da de inicio no proprio formulario", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([]));
    const create = vi.spyOn(api.campaigns, "create");
    const user = userEvent.setup();
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    await screen.findByRole("heading", { name: "Nenhuma campanha ainda" });

    await user.click(screen.getByRole("button", { name: "Nova campanha" }));
    await user.type(screen.getByLabelText("Título"), "Festa");
    await user.type(screen.getByLabelText(/Começa em/), "2026-07-01");
    await user.type(screen.getByLabelText(/Termina em/), "2026-06-01");
    await user.click(screen.getByRole("button", { name: "Criar rascunho" }));

    expect(screen.getByText("A data de fim não pode ser antes da data de início.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("cria um rascunho e abre a pagina dele, na aba dos produtos", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([]));
    const create = vi.spyOn(api.campaigns, "create").mockResolvedValue({ ok: true, data: detail() });
    const user = userEvent.setup();
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    await screen.findByRole("heading", { name: "Nenhuma campanha ainda" });

    await user.click(screen.getByRole("button", { name: "Nova campanha" }));
    await user.type(screen.getByLabelText("Título"), "  Festa Junina  ");
    await user.type(screen.getByLabelText(/Texto para as famílias/), "Barracas e jogos");
    await user.click(screen.getByRole("button", { name: "Criar rascunho" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith(SCHOOL_ID, { title: "Festa Junina", description: "Barracas e jogos", startsOn: undefined, endsOn: undefined, askStudentClass: true }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/painel/campanhas/${CAMPAIGN_ID}?aba=produtos`));
  });

  it("a campanha pede o aluno e a turma por padrao, e a gestao pode desligar", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([]));
    const create = vi.spyOn(api.campaigns, "create").mockResolvedValue({ ok: true, data: detail() });
    const user = userEvent.setup();
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    await screen.findByRole("heading", { name: "Nenhuma campanha ainda" });

    await user.click(screen.getByRole("button", { name: "Nova campanha" }));
    const ask = screen.getByRole("checkbox", { name: /Pedir o aluno e a turma/ });
    expect(ask).toBeChecked();
    await user.click(ask);
    await user.type(screen.getByLabelText("Título"), "Rifa");
    await user.click(screen.getByRole("button", { name: "Criar rascunho" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith(SCHOOL_ID, expect.objectContaining({ title: "Rifa", askStudentClass: false })));
  });

  it("erro da API aparece no formulario e nada e criado", async () => {
    vi.spyOn(api.campaigns, "list").mockResolvedValue(ok([]));
    vi.spyOn(api.campaigns, "create").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "validation_error", fields: [{ field: "title", code: "invalid" }] } });
    const user = userEvent.setup();
    render(<CampaignsBoard schoolId={SCHOOL_ID} />);
    await screen.findByRole("heading", { name: "Nenhuma campanha ainda" });

    await user.click(screen.getByRole("button", { name: "Nova campanha" }));
    await user.type(screen.getByLabelText("Título"), "Festa");
    await user.click(screen.getByRole("button", { name: "Criar rascunho" }));

    expect(await screen.findByText("O título precisa ter de 1 a 120 caracteres.")).toBeInTheDocument();
  });
});
