import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { FindSchoolForm } from "./FindSchoolForm";

async function submit(value: string) {
  const user = userEvent.setup();
  if (value) await user.type(screen.getByLabelText("Código da escola"), value);
  await user.click(screen.getByRole("button", { name: /Continuar/ }));
}

beforeEach(() => router.push.mockReset());

describe("FindSchoolForm", () => {
  it("leva ao portal da escola com o codigo digitado", async () => {
    render(<FindSchoolForm />);
    await submit("demo-aurora");
    expect(router.push).toHaveBeenCalledWith("/escola/demo-aurora");
  });

  it("aceita maiusculas, espacos e o link inteiro colado", async () => {
    render(<FindSchoolForm />);
    await submit("  https://apm.exemplo.com.br/escola/Demo-Aurora?x=1 ");
    expect(router.push).toHaveBeenCalledWith("/escola/demo-aurora");
  });

  it("vazio: avisa e nao navega", async () => {
    render(<FindSchoolForm />);
    await submit("");
    expect(screen.getByText("Informe o código da sua escola.")).toBeInTheDocument();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("codigo com caracteres que um link nunca tem: avisa e nao navega", async () => {
    render(<FindSchoolForm />);
    await submit("escola nova!");
    expect(screen.getByText(/não parece certo/)).toBeInTheDocument();
    expect(router.push).not.toHaveBeenCalled();
  });
});
