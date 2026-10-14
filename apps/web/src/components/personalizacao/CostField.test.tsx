import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { CostField } from "./CostField";

function Harness({ start }: { start: number | null }) {
  const [value, setValue] = useState<number | null>(start);
  return (
    <>
      <CostField name="cost" value={value} onChange={setValue} />
      <output data-testid="cents">{value === null ? "null" : value}</output>
    </>
  );
}

describe("custo por unidade", () => {
  it("vazio quer dizer 'nao informado' (null), nao zero", () => {
    render(<Harness start={null} />);
    expect(screen.getByLabelText(/Custo por unidade/)).toHaveValue("");
    expect(screen.getByTestId("cents")).toHaveTextContent("null");
  });

  it("digitar vira centavos, com a virgula no lugar", async () => {
    const user = userEvent.setup();
    render(<Harness start={null} />);
    await user.type(screen.getByLabelText(/Custo por unidade/), "350");
    expect(screen.getByLabelText(/Custo por unidade/)).toHaveValue("3,50");
    expect(screen.getByTestId("cents")).toHaveTextContent("350");
  });

  it("R$ 0,00 e um custo valido (um brinde) e e diferente de vazio", async () => {
    const user = userEvent.setup();
    render(<Harness start={null} />);
    await user.type(screen.getByLabelText(/Custo por unidade/), "0");
    expect(screen.getByLabelText(/Custo por unidade/)).toHaveValue("0,00");
    expect(screen.getByTestId("cents")).toHaveTextContent("0");
  });

  it("limpar o campo volta para 'nao informado'; o valor que ja existia aparece formatado", async () => {
    const user = userEvent.setup();
    render(<Harness start={1250} />);
    expect(screen.getByLabelText(/Custo por unidade/)).toHaveValue("12,50");
    await user.clear(screen.getByLabelText(/Custo por unidade/));
    expect(screen.getByTestId("cents")).toHaveTextContent("null");
  });

  it("ignora o que nao e numero", async () => {
    const user = userEvent.setup();
    render(<Harness start={null} />);
    await user.type(screen.getByLabelText(/Custo por unidade/), "a1b2");
    expect(screen.getByTestId("cents")).toHaveTextContent("12");
  });
});
