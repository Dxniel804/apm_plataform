import { describe, expect, it } from "vitest";
import { balancetePdfHref, parseBalancete } from "./balancete";

const place = (bank: number, cash: number, invested: number) => ({ bank_cents: bank, cash_cents: cash, investment_cents: invested, total_cents: bank + cash + invested });

const body = (over: Record<string, unknown> = {}) => ({
  period: "2026-07",
  opening: place(8000, 1500, 500),
  revenue: [{ name: "Contribuição de pais", cents: 5000 }],
  total_revenue_cents: 5000,
  capital: [{ name: "Compra de móveis", cents: 800 }],
  total_capital_cents: 800,
  expenses: [{ name: "Tarifas bancárias", cents: 217 }],
  total_expenses_cents: 217,
  balance_of_month_cents: 12983,
  closing: place(10983, 1500, 500),
  closing_typed: false,
  has_opening: true,
  ...over,
});

describe("parseBalancete", () => {
  it("le a folha como a API a manda", () => {
    const sheet = parseBalancete(body());
    expect(sheet?.period).toBe("2026-07");
    expect(sheet?.opening.totalCents).toBe(10000);
    expect(sheet?.revenue).toEqual([{ name: "Contribuição de pais", cents: 5000 }]);
    expect(sheet?.closing.bankCents).toBe(10983);
    expect(sheet?.closingTyped).toBe(false);
    expect(sheet?.hasOpening).toBe(true);
  });

  it("recusa o que nao e uma folha: mes torto, valor que nao e inteiro, linha sem nome, flag que nao e booleano", () => {
    expect(parseBalancete(body({ period: "2026-13" }))).toBeNull();
    expect(parseBalancete(body({ total_revenue_cents: 50.5 }))).toBeNull();
    expect(parseBalancete(body({ revenue: [{ name: "", cents: 1 }] }))).toBeNull();
    expect(parseBalancete(body({ closing_typed: "no" }))).toBeNull();
    expect(parseBalancete(body({ opening: { bank_cents: 1 } }))).toBeNull();
    expect(parseBalancete(null)).toBeNull();
  });
});

describe("balancetePdfHref", () => {
  it("e uma navegacao para o PDF do mes da escola, com o id escapado", () => {
    expect(balancetePdfHref("a b", "2026-07")).toBe("/api/v1/schools/a%20b/balancete.pdf?period=2026-07");
  });
});
