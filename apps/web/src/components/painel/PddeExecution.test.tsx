import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { PddeAlert, PddeProgramBalance } from "@/lib/api/pdde";
import { PddeExecution } from "./PddeExecution";

const program = (over: Partial<PddeProgramBalance> = {}): PddeProgramBalance => ({
  program: "BASICO", programLabel: null, receivedCents: 600_000, yieldCents: 0, returnedCents: 0, spentCusteioCents: 100_000, spentCapitalCents: 200_000, balanceCents: 300_000, ...over,
});
const conectado = program({ program: "CONECTADO", receivedCents: 100_000, spentCusteioCents: 0, spentCapitalCents: 0, balanceCents: 100_000 });
const over = (): PddeAlert => ({ code: "spent_over_received", count: 0, cents: 63_000, program: "BASICO", economicCategory: "CAPITAL", date: null });

describe("Execucao por programa", () => {
  it("uma barra so: custeio, capital e saldo, cada um com a porcentagem e o valor do servidor", () => {
    render(<PddeExecution programs={[program()]} alerts={[]} />);
    expect(screen.getByRole("img", { name: "Execução do PDDE: Custeio gasto 17%, Capital gasto 33%, Saldo 50%" })).toBeInTheDocument();
    const legend = screen.getByRole("list");
    expect(legend).toHaveTextContent(/Custeio gasto\s*R\$\s1\.000,00/);
    expect(legend).toHaveTextContent(/Capital gasto\s*R\$\s2\.000,00/);
    expect(legend).toHaveTextContent(/Saldo\s*R\$\s3\.000,00/);
    // One program: nothing to choose.
    expect(screen.queryByLabelText("Programa")).not.toBeInTheDocument();
  });

  it("'Todos' soma os programas e o seletor mostra um de cada vez", async () => {
    render(<PddeExecution programs={[program(), conectado]} alerts={[]} />);
    expect(screen.getByRole("list")).toHaveTextContent(/Saldo\s*R\$\s4\.000,00/); // 3.000 + 1.000
    await userEvent.setup().selectOptions(screen.getByLabelText("Programa"), "CONECTADO-");
    expect(screen.getByRole("list")).toHaveTextContent(/Saldo\s*R\$\s1\.000,00/);
    expect(screen.queryByText(/Custeio gasto/)).not.toBeInTheDocument(); // nothing spent there: no stretch, no row
  });

  it("gastou mais do que entrou: o aviso do servidor aparece enquanto o programa esta na tela", async () => {
    render(<PddeExecution programs={[program(), conectado]} alerts={[over()]} />);
    expect(screen.getByRole("note")).toHaveTextContent(/PDDE Básico: R\$\s630,00 de capital a mais do que entrou/);
    await userEvent.setup().selectOptions(screen.getByLabelText("Programa"), "CONECTADO-");
    expect(within(document.body).queryByRole("note")).not.toBeInTheDocument();
  });

  it("sem programas: nao desenha nada", () => {
    const { container } = render(<PddeExecution programs={[]} alerts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
