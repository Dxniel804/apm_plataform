import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { listCampaignOrders, parseDashboard } from "@/lib/api/campaigns";
import type { CampaignDashboard } from "@/lib/api/types";
import { CAMPAIGN_ID, dashboardBody, detail, orderPageBody } from "@/test-utils/campaign-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { CampaignPage } from "./CampaignPage";

const dashboard = (overrides: Record<string, unknown> = {}) => parseDashboard(dashboardBody(overrides)) as CampaignDashboard;

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(window.history, "replaceState").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("pagina da campanha", () => {
  it("mostra o titulo, a situacao e as tres abas, e abre no resumo", async () => {
    vi.spyOn(api.campaigns, "dashboard").mockResolvedValue({ ok: true, data: dashboard() });
    render(<CampaignPage schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} initialTab="resumo" />);

    expect(await screen.findByRole("heading", { name: "Festa Junina" })).toBeInTheDocument();
    expect(screen.getByText("À venda")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resumo" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Pedidos" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Produtos" })).toBeInTheDocument();
    expect(screen.getByText("Vendidos por produto")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Todas as campanhas/ })).toHaveAttribute("href", "/painel/campanhas");
  });

  it("a aba pedida na URL abre direto (?aba=produtos) e o editor carrega a campanha", async () => {
    vi.spyOn(api.campaigns, "dashboard").mockResolvedValue({ ok: true, data: dashboard({ status: "DRAFT" }) });
    const get = vi.spyOn(api.campaigns, "get").mockResolvedValue({ ok: true, data: detail() });
    render(<CampaignPage schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} initialTab="produtos" />);

    expect(await screen.findByRole("heading", { name: "Texto e datas" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID);
    expect(screen.getByRole("tab", { name: "Produtos" })).toHaveAttribute("aria-selected", "true");
  });

  it("trocar de aba mostra os pedidos, atualiza o endereco e nao recarrega os numeros", async () => {
    const board = vi.spyOn(api.campaigns, "dashboard").mockResolvedValue({ ok: true, data: dashboard() });
    const body = JSON.stringify(orderPageBody());
    const orders = await listCampaignOrders(SCHOOL_ID, CAMPAIGN_ID, {}, { fetchImpl: vi.fn().mockResolvedValue(new Response(body, { status: 200, headers: { "Content-Type": "application/json" } })) });
    const list = vi.spyOn(api.campaigns, "orders").mockResolvedValue(orders);
    const user = userEvent.setup();
    render(<CampaignPage schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} initialTab="resumo" />);
    await screen.findByRole("heading", { name: "Festa Junina" });

    await user.click(screen.getByRole("tab", { name: "Pedidos" }));

    expect(await screen.findByRole("list", { name: "Pedidos da campanha" })).toBeInTheDocument();
    expect(list).toHaveBeenCalled();
    expect(window.history.replaceState).toHaveBeenCalledWith(null, "", `/painel/campanhas/${CAMPAIGN_ID}?aba=pedidos`);
    expect(board).toHaveBeenCalledTimes(1);
  });

  it("campanha que nao existe: avisa e deixa voltar para a lista", async () => {
    vi.spyOn(api.campaigns, "dashboard").mockResolvedValue({ ok: false, error: { kind: "problem", status: 404, code: "not_found" } });
    render(<CampaignPage schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} initialTab="resumo" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Não encontramos esta campanha");
    expect(screen.getByRole("link", { name: /Todas as campanhas/ })).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("marcar uma entrega na aba de pedidos recarrega o resumo", async () => {
    const board = vi.spyOn(api.campaigns, "dashboard").mockResolvedValue({ ok: true, data: dashboard() });
    const body = JSON.stringify(orderPageBody());
    const first = await listCampaignOrders(SCHOOL_ID, CAMPAIGN_ID, {}, { fetchImpl: vi.fn().mockResolvedValue(new Response(body, { status: 200, headers: { "Content-Type": "application/json" } })) });
    vi.spyOn(api.campaigns, "orders").mockResolvedValue(first);
    vi.spyOn(api.campaigns, "changeDelivery").mockResolvedValue({ ok: true, data: { changed: 1, unchanged: 0, skipped: 0 } });
    const user = userEvent.setup();
    render(<CampaignPage schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} initialTab="pedidos" />);

    await user.click(await screen.findByRole("button", { name: /Marcar o pedido APM-000042 como entregue/ }));

    await waitFor(() => expect(board).toHaveBeenCalledTimes(2));
  });
});
