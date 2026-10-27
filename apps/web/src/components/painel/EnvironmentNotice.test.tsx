import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EnvironmentNotice } from "./EnvironmentNotice";

describe("EnvironmentNotice", () => {
  it("diz que e demonstracao, sem prometer o que o backend ainda nao garante", () => {
    render(<EnvironmentNotice />);
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Você está no ambiente de demonstração.");
    expect(notice).toHaveTextContent("Os dados desta escola são de demonstração.");
    expect(notice).not.toHaveTextContent("pagamento");
  });
});
