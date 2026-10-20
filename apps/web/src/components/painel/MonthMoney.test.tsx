import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { StatementSummary } from "@/lib/api/types";
import { SUMMARY } from "@/test-utils/statement-fixtures";
import { MonthMoney } from "./MonthMoney";

const widthOf = (container: HTMLElement, part: string) => container.querySelector<HTMLElement>(`[data-part=${part}]`)!.style.width;

describe("MonthMoney (Para onde foi o dinheiro)", () => {
  it("diz o que havia no mes e divide em saiu, a reembolsar e livre, com valor e porcentagem", () => {
    // 397,10 + 465,00 = 862,10 available; out 178,00; pending 45,00; free 639,10 (SUMMARY)
    const { container } = render(<MonthMoney summary={SUMMARY} />);

    expect(screen.getByText("Havia no mês").parentElement).toHaveTextContent("R$ 862,10");
    expect(screen.getByText(/Saldo inicial R\$ 397,10 \+ entradas R\$ 465,00/)).toBeInTheDocument();
    const rows = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Saiu");
    expect(rows[0]).toHaveTextContent("R$ 178,00 · 21%");
    expect(rows[1]).toHaveTextContent("A reembolsar");
    expect(rows[1]).toHaveTextContent("R$ 45,00 · 5%");
    expect(rows[2]).toHaveTextContent("Livre em caixa");
    expect(rows[2]).toHaveTextContent("R$ 639,10 · 74%");
    // the bar is only a drawing of the same three numbers
    expect(parseFloat(widthOf(container, "out")) + parseFloat(widthOf(container, "pending")) + parseFloat(widthOf(container, "free"))).toBeCloseTo(100, 5);
  });

  it("as saidas que passam do que havia: a barra nao passa de 100% e o texto diz quanto faltou", () => {
    const over: StatementSummary = { ...SUMMARY, closingBalanceCents: -2000, balanceAfterPendingCents: -6500 };
    const { container } = render(<MonthMoney summary={over} />);

    expect(screen.getByRole("note")).toHaveTextContent("faltam R$ 65,00");
    const rows = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(rows[2]).toHaveTextContent("R$ 0,00 · 0%");
    const total = ["out", "pending", "free"].reduce((sum, p) => sum + parseFloat(widthOf(container, p)), 0);
    expect(total).toBeLessThanOrEqual(100.0001);
  });

  it("mes sem movimento nao quebra (sem NaN) e nao desenha nada alem de zeros", () => {
    const empty: StatementSummary = { ...SUMMARY, openingBalanceCents: 0, totalInCents: 0, totalOutCents: 0, closingBalanceCents: 0, pendingReimbursementsCents: 0, balanceAfterPendingCents: 0 };
    const { container } = render(<MonthMoney summary={empty} />);

    expect(screen.getByText("Havia no mês").parentElement).toHaveTextContent("R$ 0,00");
    for (const p of ["out", "pending", "free"]) expect(widthOf(container, p)).toBe("0%");
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("a barra e so desenho: o que e lido esta na lista", () => {
    const { container } = render(<MonthMoney summary={SUMMARY} />);

    expect(container.querySelector('[data-part="out"]')!.parentElement).toHaveAttribute("aria-hidden", "true");
  });
});
