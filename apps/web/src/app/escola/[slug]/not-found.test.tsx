import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SchoolNotFound from "./not-found";

describe("a pagina de uma escola que nao abre", () => {
  it("explica que o link ainda nao esta no ar, sem mostrar 404 nem botoes", () => {
    render(<SchoolNotFound />);
    expect(screen.getByRole("heading", { level: 1, name: "Esta página ainda não está disponível" })).toBeInTheDocument();
    expect(screen.getByText("Link em preparação")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "O que está acontecendo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "O que fazer" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Nada foi cobrado" })).toBeInTheDocument();
    expect(screen.queryByText("404")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
