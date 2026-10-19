import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseBalancete, type Balancete } from "@/lib/api/balancete";
import type { ApiResult } from "@/lib/api/types";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { BalanceteCard } from "./BalanceteCard";

const place = (bank: number, cash: number, invested: number) => ({ bank_cents: bank, cash_cents: cash, investment_cents: invested, total_cents: bank + cash + invested });
const sheet = (over: Record<string, unknown> = {}) =>
  parseBalancete({
    period: "2026-07",
    opening: place(8000, 1500, 500),
    revenue: [{ name: "Contribuição de pais", cents: 5000 }],
    total_revenue_cents: 5000,
    capital: [],
    total_capital_cents: 0,
    expenses: [{ name: "Tarifas bancárias", cents: 217 }],
    total_expenses_cents: 217,
    balance_of_month_cents: 14783,
    closing: place(12783, 1500, 500),
    closing_typed: true,
    has_opening: true,
    ...over,
  }) as Balancete;
const ok = (data: Balancete): ApiResult<Balancete> => ({ ok: true, data });

afterEach(() => vi.restoreAllMocks());

describe("BalanceteCard", () => {
  it("mostra a folha na ordem da contadora e o link do PDF", async () => {
    vi.spyOn(api.balancete, "get").mockResolvedValue(ok(sheet()));
    render(<BalanceteCard schoolId={SCHOOL_ID} canType={false} />);

    const body = await screen.findByTestId("balancete");
    expect(body).toHaveTextContent("Saldo anterior");
    expect(body).toHaveTextContent("Contribuição de pais");
    expect(body).toHaveTextContent("Total de receitas");
    expect(body).toHaveTextContent("Tarifas bancárias");
    expect(body).toHaveTextContent("Saldo do mês");
    expect(body).toHaveTextContent("Demonstração do saldo final");
    expect(screen.getByRole("link", { name: /Balancete \(PDF/ })).toHaveAttribute("href", expect.stringContaining("/balancete.pdf?period="));
    expect(screen.queryByRole("button", { name: "Salvar caixa e aplicação" })).toBeNull();
  });

  it("avisa quando caixa, aplicacao ou o saldo inicial ainda nao foram informados", async () => {
    vi.spyOn(api.balancete, "get").mockResolvedValue(ok(sheet({ closing_typed: false, has_opening: false })));
    render(<BalanceteCard schoolId={SCHOOL_ID} canType={false} />);

    expect(await screen.findByText(/Caixa e aplicação deste mês ainda não foram informados/)).toBeInTheDocument();
    expect(screen.getByText(/saldo de quando a escola começou a usar o sistema ainda não foi informado/)).toBeInTheDocument();
  });

  it("quem fecha o mes salva o caixa e a aplicacao, e a folha e lida de novo", async () => {
    const get = vi.spyOn(api.balancete, "get").mockResolvedValue(ok(sheet()));
    const set = vi.spyOn(api.balancete, "set").mockResolvedValue({ ok: true, data: { status: "saved" } });
    const user = userEvent.setup();
    render(<BalanceteCard schoolId={SCHOOL_ID} canType />);
    await screen.findByTestId("balancete");

    await user.click(screen.getByRole("button", { name: "Salvar caixa e aplicação" }));

    await waitFor(() => expect(set).toHaveBeenCalledTimes(1));
    expect(set.mock.calls[0]![1]).toMatchObject({ kind: "MONTH", cashCents: 1500, investmentCents: 500 });
    expect(await screen.findByText(/salvos\./)).toBeInTheDocument();
    expect(get.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("o banco negativo vira aviso e uma recusa da API vira texto, sem o codigo", async () => {
    vi.spyOn(api.balancete, "get").mockResolvedValue(ok(sheet({ closing: place(-100, 1500, 500) })));
    vi.spyOn(api.balancete, "set").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "balance_refused" } });
    const user = userEvent.setup();
    render(<BalanceteCard schoolId={SCHOOL_ID} canType />);

    expect(await screen.findByText(/O banco ficou negativo/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Salvar caixa e aplicação" }));
    expect(await screen.findByText("Confira os valores digitados.")).toBeInTheDocument();
    expect(screen.queryByText(/balance_refused/)).toBeNull();
  });
});
