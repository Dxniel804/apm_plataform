import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SUMMARY } from "@/test-utils/statement-fixtures";
import type { StatementSummary } from "@/lib/api/types";
import { BalanceChart } from "./BalanceChart";
import { OutflowSplit } from "./OutflowSplit";

const barOf = (item: HTMLElement) => item.querySelector<HTMLElement>("span[style]")!;
const lo = (item: HTMLElement) => Number(barOf(item).style.getPropertyValue("--lo"));
const hi = (item: HTMLElement) => Number(barOf(item).style.getPropertyValue("--hi"));

describe("BalanceChart (Composicao do saldo)", () => {
  it("mostra as 6 etapas, na ordem, com os numeros da API e sinais do Figma", () => {
    render(<BalanceChart summary={SUMMARY} />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "Saldo inicial397,10",
      "Entradas+465,00",
      "Saídas-178,00",
      "Saldo em caixa684,10",
      "A reembolsar-45,00",
      "Após pendências639,10",
    ]);
  });

  it("as barras de saldo partem do zero e as de variacao flutuam entre os dois niveis", () => {
    render(<BalanceChart summary={SUMMARY} />);
    const [open, inflow, outflow, close, pending, after] = screen.getAllByRole("listitem");
    expect(lo(open!)).toBe(0);
    expect(lo(close!)).toBe(0);
    expect(lo(after!)).toBe(0);
    // entradas: de saldo inicial ate saldo inicial + entradas
    expect(lo(inflow!)).toBeCloseTo(lo(open!) + (hi(open!) - lo(open!)), 5);
    expect(hi(inflow!)).toBeGreaterThan(hi(open!));
    // saidas: termina no saldo em caixa e sobe o tamanho das saidas
    expect(lo(outflow!)).toBeCloseTo(hi(close!), 5);
    // reembolsos pendentes: entre o saldo depois e o saldo em caixa
    expect(lo(pending!)).toBeCloseTo(hi(after!), 5);
    expect(hi(pending!)).toBeCloseTo(hi(close!), 5);
    // a maior barra ocupa 100%
    expect(Math.max(...[open, inflow, outflow, close, pending, after].map((i) => hi(i!)))).toBeCloseTo(100, 5);
  });

  it("as barras sao decoracao: nada nelas e anunciado alem do texto", () => {
    render(<BalanceChart summary={SUMMARY} />);
    const first = screen.getAllByRole("listitem")[0]!;
    expect(first.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it("mes sem movimento e saldo negativo nao quebram (sem NaN)", () => {
    const empty: StatementSummary = { ...SUMMARY, openingBalanceCents: 0, totalInCents: 0, totalOutCents: 0, closingBalanceCents: 0, pendingReimbursementsCents: 0, balanceAfterPendingCents: 0 };
    const { unmount } = render(<BalanceChart summary={empty} />);
    for (const li of screen.getAllByRole("listitem")) expect(Number.isFinite(hi(li))).toBe(true);
    unmount();
    const negative: StatementSummary = { ...SUMMARY, closingBalanceCents: -2000, balanceAfterPendingCents: -6500 };
    render(<BalanceChart summary={negative} />);
    for (const li of screen.getAllByRole("listitem")) {
      expect(Number.isFinite(lo(li))).toBe(true);
      expect(Number.isFinite(hi(li))).toBe(true);
    }
    expect(within(screen.getAllByRole("listitem")[3]!).getByText("-20,00")).toBeInTheDocument();
  });
});

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
