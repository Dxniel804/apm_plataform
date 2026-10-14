import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseDashboard } from "@/lib/api/campaigns";
import type { CampaignDashboard } from "@/lib/api/types";
import { CAMPAIGN_ID, ITEM_A, dashboardBody } from "@/test-utils/campaign-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";

const saveBlob = vi.hoisted(() => vi.fn());
vi.mock("@/lib/download", () => ({ saveBlob }));

import { CampaignSummaryTab } from "./CampaignSummaryTab";

const dashboard = (overrides: Record<string, unknown> = {}) => parseDashboard(dashboardBody(overrides)) as CampaignDashboard;

beforeEach(() => saveBlob.mockReset());
afterEach(() => vi.restoreAllMocks());

describe("resumo da campanha", () => {
  it("mostra arrecadado, custos, lucro, unidades, pedidos e entregas, como a API calculou", () => {
    render(<CampaignSummaryTab schoolId={SCHOOL_ID} dashboard={dashboard()} />);

    expect(screen.getByText("Arrecadado", { selector: "p" }).nextElementSibling).toHaveTextContent("R$ 30,50");
    expect(screen.getByText("2 pedidos aprovados")).toBeInTheDocument();
    expect(screen.getByText("Custos", { selector: "p" }).nextElementSibling).toHaveTextContent("R$ 11,00");
    expect(screen.getByText("Lucro", { selector: "p" }).nextElementSibling).toHaveTextContent("R$ 19,50");
    expect(screen.getByText("Unidades vendidas", { selector: "p" }).nextElementSibling).toHaveTextContent("4");
    expect(screen.getByText("Pedidos por pagamento", { selector: "p" }).nextElementSibling).toHaveTextContent("3");
    expect(screen.getByText("1 pendente · 0 cancelados")).toBeInTheDocument();
    expect(screen.getByText("Entregas", { selector: "p" }).nextElementSibling).toHaveTextContent("1 de 2");
  });

  it("vendidos por produto: unidades, arrecadado e custo de cada um", () => {
    render(<CampaignSummaryTab schoolId={SCHOOL_ID} dashboard={dashboard()} />);
    const table = screen.getByRole("table");
    const row = within(table).getByRole("row", { name: /Cachorro-quente/ });
    expect(row).toHaveTextContent("3");
    expect(row).toHaveTextContent("R$ 24,00");
    expect(row).toHaveTextContent("R$ 9,00");
  });

  it("sem custo em algum produto vendido: nao inventa lucro, diz 'custo nao informado'", () => {
    render(
      <CampaignSummaryTab
        schoolId={SCHOOL_ID}
        dashboard={dashboard({ cost_complete: false, profit_cents: null, cost_cents: 900, items: [{ item_id: ITEM_A, name: "Pamonha", units_sold: 1, revenue_cents: 650, cost_cents: null, cost_known: false }] })}
      />,
    );
    expect(screen.getByText("Lucro", { selector: "p" }).nextElementSibling).toHaveTextContent("custo não informado");
    expect(screen.getByText("Custos", { selector: "p" }).nextElementSibling).toHaveTextContent("R$ 9,00 informados");
    expect(within(screen.getByRole("table")).getByRole("row", { name: /Pamonha/ })).toHaveTextContent("não informado");
    expect(screen.queryByText("R$ 19,50")).not.toBeInTheDocument();
  });

  it("lembra que o custo nao e lancamento no caixa", () => {
    render(<CampaignSummaryTab schoolId={SCHOOL_ID} dashboard={dashboard()} />);
    expect(screen.getByText(/não é um lançamento no caixa/)).toBeInTheDocument();
  });

  it("baixa o PDF da campanha pela API e salva o arquivo", async () => {
    const report = vi.spyOn(api.campaigns, "report").mockResolvedValue({ ok: true, data: { blob: new Blob(["%PDF"], { type: "application/pdf" }), contentType: "application/pdf" } });
    const user = userEvent.setup();
    render(<CampaignSummaryTab schoolId={SCHOOL_ID} dashboard={dashboard()} />);

    await user.click(screen.getByRole("button", { name: "Baixar PDF da campanha" }));

    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(expect.anything(), `campanha-${CAMPAIGN_ID.slice(0, 8)}.pdf`));
    expect(report).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID);
  });

  it("erro ao gerar o PDF vira texto e nada e salvo", async () => {
    vi.spyOn(api.campaigns, "report").mockResolvedValue({ ok: false, error: { kind: "network" } });
    const user = userEvent.setup();
    render(<CampaignSummaryTab schoolId={SCHOOL_ID} dashboard={dashboard()} />);

    await user.click(screen.getByRole("button", { name: "Baixar PDF da campanha" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Nada foi alterado");
    expect(saveBlob).not.toHaveBeenCalled();
  });
});
