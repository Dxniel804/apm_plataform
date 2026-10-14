import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiResult, CampaignOrderPage } from "@/lib/api/types";
import { CAMPAIGN_ID, ORDER_1, ORDER_2, ORDER_3, orderBody, orderPageBody } from "@/test-utils/campaign-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { CampaignOrders } from "./CampaignOrders";

/** A pagina de pedidos como a API a devolve, passada pelo parser do site. */
async function page(items: unknown[], overrides: Record<string, unknown> = {}): Promise<ApiResult<CampaignOrderPage>> {
  const { listCampaignOrders } = await import("@/lib/api/campaigns");
  const body = JSON.stringify(orderPageBody(items, overrides));
  return listCampaignOrders(SCHOOL_ID, CAMPAIGN_ID, {}, { fetchImpl: vi.fn().mockResolvedValue(new Response(body, { status: 200, headers: { "Content-Type": "application/json" } })) });
}

const PAID = orderBody();
const WAITING = orderBody({ order_id: ORDER_2, reference_code: 43, payment_status: "PENDING", delivery_status: null, student_name: "Caio", class_name: "1C", guardian_name: "Joao" });
const DONE = orderBody({ order_id: ORDER_3, reference_code: 44, delivery_status: "DELIVERED", delivery_changed_at: "2026-10-14T15:00:00Z", student_name: "Beto", class_name: "5B", guardian_name: "Rita" });

afterEach(() => vi.restoreAllMocks());

describe("pedidos da campanha", () => {
  it("lista quem comprou, o que, o pagamento e a entrega, com o numero APM", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([PAID, WAITING, DONE]));
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);

    const items = within(await screen.findByRole("list", { name: "Pedidos da campanha" })).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("APM-000042");
    expect(items[0]).toHaveTextContent("Ana · 3A");
    expect(items[0]).toHaveTextContent("responsável: Maria");
    expect(items[0]).toHaveTextContent("2 × Cachorro-quente · 1 × Pamonha");
    expect(items[0]).toHaveTextContent("R$ 22,50");
    expect(items[0]).toHaveTextContent("Aprovado");
    expect(items[0]).toHaveTextContent("A entregar");
    expect(items[1]).toHaveTextContent("Pendente");
    expect(items[1]).not.toHaveTextContent("A entregar"); // pedido nao aprovado nao tem entrega
    expect(items[2]).toHaveTextContent("Entregue");
    expect(screen.getByText("Mostrando 1 a 3 de 3")).toBeInTheDocument();
  });

  it("so pedido aprovado tem caixa de marcar e botao de entrega", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([PAID, WAITING, DONE]));
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Pedidos da campanha" });

    expect(screen.getByRole("checkbox", { name: "Escolher o pedido APM-000042" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Escolher o pedido APM-000043" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marcar o pedido APM-000042 como entregue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Desfazer a entrega do pedido APM-000044" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /APM-000043/ })).not.toBeInTheDocument();
  });

  it("marca a entrega de um pedido pela API e recarrega a lista e os numeros do resumo", async () => {
    const orders = vi.spyOn(api.campaigns, "orders").mockResolvedValueOnce(await page([PAID])).mockResolvedValue(await page([orderBody({ delivery_status: "DELIVERED", delivery_changed_at: "2026-10-14T15:00:00Z" })]));
    const change = vi.spyOn(api.campaigns, "changeDelivery").mockResolvedValue({ ok: true, data: { changed: 1, unchanged: 0, skipped: 0 } });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={onChanged} />);

    await user.click(await screen.findByRole("button", { name: "Marcar o pedido APM-000042 como entregue" }));

    await waitFor(() => expect(change).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, [ORDER_1], true));
    expect(await screen.findByRole("status")).toHaveTextContent("1 pedido marcado como entregue");
    await waitFor(() => expect(orders).toHaveBeenCalledTimes(2));
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("button", { name: "Desfazer a entrega do pedido APM-000042" })).toBeInTheDocument();
  });

  it("em lote: escolhe os aprovados da pagina e marca todos de uma vez; desmarcar usa o mesmo caminho", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([PAID, WAITING, DONE]));
    const change = vi.spyOn(api.campaigns, "changeDelivery").mockResolvedValue({ ok: true, data: { changed: 2, unchanged: 0, skipped: 0 } });
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Pedidos da campanha" });
    expect(screen.getByRole("button", { name: "Marcar como entregue" })).toBeDisabled(); // nada escolhido

    await user.click(screen.getByRole("checkbox", { name: /Marcar todos os aprovados desta página/ }));
    await user.click(screen.getByRole("button", { name: "Marcar como entregue (2)" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, [ORDER_1, ORDER_3], true));

    await user.click(await screen.findByRole("checkbox", { name: "Escolher o pedido APM-000042" }));
    await user.click(screen.getByRole("button", { name: "Desmarcar entrega" }));
    await waitFor(() => expect(change).toHaveBeenLastCalledWith(SCHOOL_ID, CAMPAIGN_ID, [ORDER_1], false));
  });

  it("os que a API pulou sao contados na mensagem; nada mudou vira aviso claro", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([PAID]));
    const change = vi.spyOn(api.campaigns, "changeDelivery").mockResolvedValueOnce({ ok: true, data: { changed: 1, unchanged: 0, skipped: 1 } }).mockResolvedValueOnce({ ok: true, data: { changed: 0, unchanged: 1, skipped: 0 } });
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "Marcar o pedido APM-000042 como entregue" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 não puderam mudar");
    await user.click(await screen.findByRole("button", { name: "Marcar o pedido APM-000042 como entregue" }));
    await waitFor(() => expect(change).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Nada mudou: esses pedidos já estavam assim.")).toBeInTheDocument();
  });

  it("erro da API ao marcar a entrega aparece em portugues e nada some da tela", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([PAID]));
    vi.spyOn(api.campaigns, "changeDelivery").mockResolvedValue({ ok: false, error: { kind: "network" } });
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "Marcar o pedido APM-000042 como entregue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Nada foi alterado");
    expect(screen.getByText("APM-000042", { exact: false })).toBeInTheDocument();
  });

  it("filtros de pagamento e de entrega e a busca vao para a API e voltam para a primeira pagina", async () => {
    const orders = vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([PAID]));
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Pedidos da campanha" });
    expect(orders).toHaveBeenLastCalledWith(SCHOOL_ID, CAMPAIGN_ID, { payment: undefined, delivery: undefined, search: "", limit: 25, offset: 0 });

    await user.click(screen.getByRole("button", { name: "Aprovados" }));
    await waitFor(() => expect(orders).toHaveBeenLastCalledWith(SCHOOL_ID, CAMPAIGN_ID, expect.objectContaining({ payment: "PAID" })));
    await user.click(screen.getByRole("button", { name: "A entregar" }));
    await waitFor(() => expect(orders).toHaveBeenLastCalledWith(SCHOOL_ID, CAMPAIGN_ID, expect.objectContaining({ payment: "PAID", delivery: "PENDING" })));
    await user.type(screen.getByLabelText("Buscar"), "Ana");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(orders).toHaveBeenLastCalledWith(SCHOOL_ID, CAMPAIGN_ID, expect.objectContaining({ search: "Ana", offset: 0 })));
  });

  it("paginas: Proximos pede o proximo bloco e Anteriores volta", async () => {
    const many = Array.from({ length: 25 }, (_, i) => orderBody({ order_id: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`, reference_code: 100 + i }));
    const orders = vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page(many, { total: 40 }));
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    await screen.findByText("Mostrando 1 a 25 de 40");
    expect(screen.getByRole("button", { name: "Anteriores" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Próximos" }));
    await waitFor(() => expect(orders).toHaveBeenLastCalledWith(SCHOOL_ID, CAMPAIGN_ID, expect.objectContaining({ offset: 25 })));
  });

  it("sem pedidos: explica; com filtro sem resultado: pede para tirar o filtro", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(await page([], { total: 0 }));
    const user = userEvent.setup();
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    expect(await screen.findByText(/Quando as famílias fizerem pedidos/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelados" }));
    expect(await screen.findByText(/Nenhum pedido combina com esse filtro/)).toBeInTheDocument();
  });

  it("erro ao carregar os pedidos vira texto em portugues", async () => {
    vi.spyOn(api.campaigns, "orders").mockResolvedValue({ ok: false, error: { kind: "problem", status: 403, code: "permission_denied" } });
    render(<CampaignOrders schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("não tem permissão");
  });
});
