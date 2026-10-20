import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseBuyers } from "@/lib/api/campaigns";
import type { ApiResult, CampaignBuyerList } from "@/lib/api/types";
import { CampaignBuyers } from "./CampaignBuyers";

const ok = <T,>(data: T): ApiResult<T> => ({ ok: true, data });
const body = {
  complete: true,
  items: [
    { guardian_name: "João Lima", student_name: "Beto", class_name: "5º ano B", orders: 1, units: 3, amount_cents: 1950, lines: [{ item_name: "Pamonha", quantity: 3 }] },
    {
      guardian_name: "Maria Souza", student_name: "Ana", class_name: "3º ano A", orders: 2, units: 4, amount_cents: 3050,
      lines: [{ item_name: "Cachorro-quente", quantity: 3 }, { item_name: "Pamonha", quantity: 1 }],
    },
  ],
};
const list = parseBuyers(body) as CampaignBuyerList;

afterEach(() => vi.restoreAllMocks());

describe("CampaignBuyers", () => {
  it("mostra cada responsavel com o aluno, a quantidade de cada produto e o total", async () => {
    vi.spyOn(api.campaigns, "buyers").mockResolvedValue(ok(list));
    render(<CampaignBuyers schoolId="s1" campaignId="c1" />);

    const rows = within(await screen.findByRole("list", { name: "Quem comprou" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("Maria Souza");
    expect(rows[1]).toHaveTextContent("Ana · 3º ano A");
    expect(rows[1]).toHaveTextContent("3 × Cachorro-quente · 1 × Pamonha");
    expect(rows[1]).toHaveTextContent("R$ 30,50");
    expect(rows[1]).toHaveTextContent("4 unidades em 2 pedidos");
  });

  it("a busca acha pelo responsavel, pelo aluno ou pela turma, sem acento nem caixa", async () => {
    vi.spyOn(api.campaigns, "buyers").mockResolvedValue(ok(list));
    const user = userEvent.setup();
    render(<CampaignBuyers schoolId="s1" campaignId="c1" />);
    await screen.findByRole("list", { name: "Quem comprou" });

    await user.type(screen.getByLabelText(/Buscar/), "joao");
    expect(within(screen.getByRole("list", { name: "Quem comprou" })).getAllByRole("listitem")).toHaveLength(1);

    await user.clear(screen.getByLabelText(/Buscar/));
    await user.type(screen.getByLabelText(/Buscar/), "3º ano");
    expect(screen.getByText("Maria Souza")).toBeInTheDocument();
    expect(screen.queryByText("João Lima")).toBeNull();

    await user.clear(screen.getByLabelText(/Buscar/));
    await user.type(screen.getByLabelText(/Buscar/), "zzz");
    expect(screen.getByText("Ninguém com esse nome.")).toBeInTheDocument();
  });

  it("sem pedido aprovado, diz isso; com erro, avisa", async () => {
    vi.spyOn(api.campaigns, "buyers").mockResolvedValueOnce(ok({ items: [], complete: true }));
    const { unmount } = render(<CampaignBuyers schoolId="s1" campaignId="c1" />);
    expect(await screen.findByText("Nenhum pedido aprovado ainda.")).toBeInTheDocument();
    unmount();

    vi.spyOn(api.campaigns, "buyers").mockResolvedValueOnce({ ok: false, error: { kind: "problem", status: 500, code: "x" } });
    render(<CampaignBuyers schoolId="s1" campaignId="c1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar quem comprou.");
  });

  it("avisa quando ha mais pedidos do que os contados", async () => {
    vi.spyOn(api.campaigns, "buyers").mockResolvedValue(ok({ ...list, complete: false }));
    render(<CampaignBuyers schoolId="s1" campaignId="c1" />);

    expect(await screen.findByText(/os 5\.000 mais recentes/)).toBeInTheDocument();
  });

  it("o parser recusa uma resposta que nao e a lista", () => {
    expect(parseBuyers({ items: "x", complete: true })).toBeNull();
    expect(parseBuyers({ items: [{ guardian_name: "A", orders: 1 }], complete: true })).toBeNull();
    expect(parseBuyers(body)?.items[0]).toMatchObject({ guardianName: "João Lima", units: 3, amountCents: 1950 });
  });
});
