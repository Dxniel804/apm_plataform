import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Amount } from "./Amount";

describe("Amount", () => {
  it("o leitor de tela ouve o valor inteiro uma unica vez; a versao em dois tons fica escondida dele", () => {
    const { container } = render(<Amount cents={235858} />);
    expect(screen.getByText("R$ 2.358,58")).toHaveClass("sr-only");
    const visual = container.querySelector('[aria-hidden="true"]');
    expect(visual).toHaveTextContent("R$ 2.358,58");
    expect(visual?.querySelector("span")).toHaveTextContent("R$");
  });

  it("negativo: o sinal vem antes do simbolo", () => {
    const { container } = render(<Amount cents={-1250} />);
    expect(screen.getByText("-R$ 12,50")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toHaveTextContent("-R$ 12,50");
  });
});
