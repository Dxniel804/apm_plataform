import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SandboxGate } from "./SandboxGate";

describe("SandboxGate", () => {
  it("escola em demonstracao: mostra o card e so depois de 'Entendi' a contribuicao", async () => {
    render(
      <SandboxGate active>
        <p>Formulario de contribuicao</p>
      </SandboxGate>,
    );
    expect(screen.getByRole("heading", { name: "Ambiente de demonstração" })).toBeInTheDocument();
    expect(screen.getByText(/fictícios/)).toBeInTheDocument();
    expect(screen.queryByText("Formulario de contribuicao")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Entendi, continuar" }));

    expect(screen.getByText("Formulario de contribuicao")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ambiente de demonstração" })).not.toBeInTheDocument();
  });

  it("escola em producao (ou sem a informacao da Central): nada muda, a contribuicao abre direto", () => {
    render(
      <SandboxGate active={false}>
        <p>Formulario de contribuicao</p>
      </SandboxGate>,
    );
    expect(screen.getByText("Formulario de contribuicao")).toBeInTheDocument();
    expect(screen.queryByText(/demonstração/)).not.toBeInTheDocument();
  });
});
