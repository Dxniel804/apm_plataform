import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GoalAdhesion } from "@/lib/api/types";
import { GoalCard } from "./GoalCard";

const goal = (o: Partial<GoalAdhesion> = {}): GoalAdhesion => ({ period: "2026-10", goalCents: 1_000_000, collectedCents: 250_000, expectedContributions: 80, paidContributions: 20, ...o });

describe("Meta e adesao", () => {
  it("mostra o arrecadado contra a meta e as contribuicoes pagas contra as esperadas, em porcentagem", () => {
    render(<GoalCard goal={goal()} canConfigure />);
    expect(screen.getByRole("progressbar", { name: "Arrecadado" })).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText("R$ 2.500,00 de R$ 10.000,00")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Contribuições pagas" })).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText("20 de 80 esperadas")).toBeInTheDocument();
  });

  it("fala de contribuicoes, nunca de familias", () => {
    render(<GoalCard goal={goal()} canConfigure />);
    expect(document.body.textContent).not.toMatch(/fam[ií]lias (pagaram|aderiram)/i);
    expect(screen.getByText(/Contribuições pagas/)).toBeInTheDocument();
  });

  it("passou da meta: a barra para em 100%", () => {
    render(<GoalCard goal={goal({ collectedCents: 3_000_000 })} canConfigure />);
    expect(screen.getByRole("progressbar", { name: "Arrecadado" })).toHaveAttribute("aria-valuenow", "100");
  });

  it("sem meta: convida a definir em Configuracoes, so para quem pode", () => {
    const { rerender } = render(<GoalCard goal={goal({ goalCents: null, expectedContributions: null })} canConfigure />);
    expect(screen.getByRole("link", { name: "Definir em Configurações" })).toHaveAttribute("href", "/painel/configuracoes");
    rerender(<GoalCard goal={goal({ goalCents: null, expectedContributions: null })} canConfigure={false} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText(/ainda não definiu a meta/)).toBeInTheDocument();
  });
});

describe("tarifas do gateway (M4)", () => {
  it("o resumo traz as tarifas do mes; uma API antiga, sem o campo, vira zero", async () => {
    const { parseSummary } = await import("@/lib/api/statement");
    const { SUMMARY_BODY } = await import("@/test-utils/statement-fixtures");
    expect(parseSummary({ ...SUMMARY_BODY, gateway_fees_cents: 160 })).toMatchObject({ gatewayFeesCents: 160 });
    const { gateway_fees_cents: _ignored, ...old } = { ...SUMMARY_BODY, gateway_fees_cents: 0 };
    void _ignored;
    expect(parseSummary(old)).toMatchObject({ gatewayFeesCents: 0 });
    expect(parseSummary({ ...SUMMARY_BODY, gateway_fees_cents: "x" })).toBeNull();
  });

  it("o lancamento mostra a tarifa e o liquido quando existem", async () => {
    const { render: r, screen: s } = await import("@testing-library/react");
    const { entry } = await import("@/test-utils/statement-fixtures");
    const { StatementList } = await import("./StatementList");
    r(<StatementList entries={[entry({ gatewayFeeCents: 80, netCents: 2920 })]} label="Contribuições" />);
    expect(s.getByText(/tarifa R\$\s?0,80 · líquido R\$\s?29,20/)).toBeInTheDocument();
  });
});
