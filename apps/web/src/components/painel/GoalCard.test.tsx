import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GoalAdhesion } from "@/lib/api/types";
import { EvolutionChart } from "./EvolutionChart";
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

describe("Evolucao do caixa", () => {
  const points = [
    { period: "2026-08", totalInCents: 10000, totalOutCents: 4000, closingBalanceCents: 6000 },
    { period: "2026-09", totalInCents: 0, totalOutCents: 0, closingBalanceCents: 6000 },
    { period: "2026-10", totalInCents: 25000, totalOutCents: 5000, closingBalanceCents: 26000 },
  ];

  it("desenha as barras e traz os mesmos valores em tabela", () => {
    render(<EvolutionChart points={points} />);
    expect(screen.getByRole("img", { name: /Entradas e saídas dos últimos 3 meses/ })).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(4); // cabecalho + 3 meses
    expect(rows[3]).toHaveTextContent("outubro de 2026");
    expect(rows[3]).toHaveTextContent("R$ 250,00");
    expect(rows[3]).toHaveTextContent("R$ 260,00");
  });

  it("sem nenhum movimento: avisa em vez de desenhar barras vazias", () => {
    render(<EvolutionChart points={points.map((p) => ({ ...p, totalInCents: 0, totalOutCents: 0 }))} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/Ainda não há movimento/)).toBeInTheDocument();
  });
});
