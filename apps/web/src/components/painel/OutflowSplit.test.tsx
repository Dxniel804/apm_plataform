import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SUMMARY } from "@/test-utils/statement-fixtures";
import { OutflowSplit } from "./OutflowSplit";

describe("OutflowSplit (Total de saidas)", () => {
  it("mostra o total do mes e cada parte com valor e porcentagem", () => {
    render(<OutflowSplit summary={{ ...SUMMARY, totalOutCents: 24000, reimbursementsOutCents: 20800, expensesOutCents: 3200 }} />);
    expect(screen.getByText("Total do mês: R$ 240,00")).toBeInTheDocument();
    expect(screen.getByText("R$ 208,00 · 87%")).toBeInTheDocument();
    expect(screen.getByText("R$ 32,00 · 13%")).toBeInTheDocument();
  });

  it("sem saidas no mes: avisa em vez de desenhar uma barra vazia", () => {
    render(<OutflowSplit summary={{ ...SUMMARY, totalOutCents: 0, reimbursementsOutCents: 0, expensesOutCents: 0 }} />);
    expect(screen.getByText("Nenhuma saída paga neste mês.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
