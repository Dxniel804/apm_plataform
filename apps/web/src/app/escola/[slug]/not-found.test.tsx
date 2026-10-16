import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SchoolNotFound from "./not-found";

describe("a pagina de uma escola que nao abre", () => {
  it("explica que o link ainda nao esta no ar, sem mostrar 404 nem botoes", () => {
    render(<SchoolNotFound />);
    expect(screen.getByRole("heading", { name: "Esta página ainda não está disponível" })).toBeInTheDocument();
    expect(screen.getByText(/ainda não está aberto para contribuições/)).toBeInTheDocument();
    expect(screen.queryByText("404")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
