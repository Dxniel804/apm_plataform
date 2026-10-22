import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BLUES, SegmentBar } from "./SegmentBar";

const seg = (key: string, weight: number, over = {}) => ({ key, label: key.toUpperCase(), weight, value: `valor ${key}`, color: BLUES[0], ...over });

describe("SegmentBar", () => {
  it("diz a porcentagem de cada trecho e escreve o valor de cada um na legenda", () => {
    render(<SegmentBar label="Teste" segments={[seg("a", 80), seg("b", 15, { meta: "(2 itens)" }), seg("c", 5)]} />);
    expect(screen.getByRole("img", { name: "Teste: A 80%, B 15%, C 5%" })).toBeInTheDocument();
    expect(screen.getByText("valor a")).toBeInTheDocument();
    expect(screen.getByText("(2 itens)")).toBeInTheDocument();
  });

  it("trecho sem peso some da barra e da legenda; sem nenhum peso, nao desenha nada", () => {
    const { container, rerender } = render(<SegmentBar label="Teste" segments={[seg("a", 10), seg("b", 0)]} />);
    expect(screen.queryByText("B")).not.toBeInTheDocument();
    rerender(<SegmentBar label="Teste" segments={[seg("a", 0)]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("com onClick a linha da legenda e um botao", async () => {
    const onClick = vi.fn();
    render(<SegmentBar label="Teste" segments={[seg("a", 10, { onClick, popup: "dialog" })]} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /A/ }));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
