import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { SeriesPoint } from "@/lib/api/types";
import { BalanceTrend } from "./BalanceTrend";

const pt = (period: string, totalInCents: number, totalOutCents: number, closingBalanceCents: number): SeriesPoint => ({ period, totalInCents, totalOutCents, closingBalanceCents });
const points = [pt("2026-08", 10000, 4000, 6000), pt("2026-09", 0, 0, 6000), pt("2026-10", 25000, 5000, 26000)];

describe("Saldo em caixa mes a mes", () => {
  it("diz o saldo de cada mes para quem nao ve o grafico e traz os mesmos valores em tabela", () => {
    render(<BalanceTrend points={points} />);
    expect(screen.getByRole("img", { name: /Saldo em caixa no fim de cada mês: ago R\$\s60,00, set R\$\s60,00, out R\$\s260,00/ })).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(4); // cabecalho + 3 meses
    expect(rows[3]).toHaveTextContent("outubro de 2026");
    expect(rows[3]).toHaveTextContent("R$ 250,00"); // entradas
    expect(rows[3]).toHaveTextContent("R$ 50,00"); // saidas
    expect(rows[3]).toHaveTextContent("R$ 260,00"); // saldo
  });

  it("mostra quanto o saldo subiu ou caiu contra o mes anterior, com palavra (nao so cor)", () => {
    const { rerender } = render(<BalanceTrend points={points} />);
    expect(screen.getByText(/Subiu R\$ 200,00 desde setembro/)).toBeInTheDocument();
    rerender(<BalanceTrend points={[pt("2026-09", 10000, 0, 30000), pt("2026-10", 0, 20000, 10000)]} />);
    expect(screen.getByText(/Caiu R\$ 200,00 desde setembro/)).toBeInTheDocument();
    rerender(<BalanceTrend points={[pt("2026-09", 10000, 0, 30000), pt("2026-10", 0, 0, 30000)]} />);
    expect(screen.queryByText(/Subiu|Caiu/)).not.toBeInTheDocument();
  });

  it("meses vazios no comeco ficam de fora (no minimo 3 meses)", () => {
    const six = [pt("2026-05", 0, 0, 0), pt("2026-06", 0, 0, 0), pt("2026-07", 0, 0, 0), pt("2026-08", 0, 0, 0), ...points.slice(1)];
    render(<BalanceTrend points={six} />);
    expect(screen.getAllByRole("row")).toHaveLength(4); // cabecalho + ago, set, out
    expect(screen.queryByText("maio de 2026")).not.toBeInTheDocument();
  });

  it("saldo negativo: o zero continua no desenho e a curva nao quebra", () => {
    render(<BalanceTrend points={[pt("2026-09", 0, 5000, -5000), pt("2026-10", 1000, 0, -4000)]} />);
    expect(screen.getByRole("img", { name: /set .*50,00/ })).toBeInTheDocument();
  });

  it("passar o mouse num mes abre o saldo, as entradas e as saidas daquele mes", async () => {
    render(<BalanceTrend points={points} />);
    await userEvent.setup().hover(screen.getByRole("button", { name: /agosto de 2026/ }));
    expect(screen.getByText("Saldo R$ 60,00")).toBeInTheDocument();
    expect(screen.getByText(/Entradas R\$ 100,00 · saídas R\$ 40,00/)).toBeInTheDocument();
  });

  it("sem nenhum movimento: avisa em vez de desenhar uma linha vazia", () => {
    render(<BalanceTrend points={points.map((p) => pt(p.period, 0, 0, 0))} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/Ainda não há movimento/)).toBeInTheDocument();
    expect(within(document.body).queryAllByRole("button")).toHaveLength(0);
  });
});
