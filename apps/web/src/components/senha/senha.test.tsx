import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiResult } from "@/lib/api/types";
import { ForgotPasswordForm } from "./ForgotPasswordForm";
import { ResetPasswordForm } from "./ResetPasswordForm";

const TOKEN = "a".repeat(43);
const NEW = "uma-senha-nova-bem-longa";
const ok: ApiResult<true> = { ok: true, data: true };

afterEach(() => vi.restoreAllMocks());

describe("Esqueci minha senha", () => {
  it("pede o e-mail e mostra a mesma frase, exista a conta ou nao", async () => {
    const ask = vi.spyOn(api.auth, "requestPasswordReset").mockResolvedValue(ok);
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText("Seu e-mail"), "alguem@escola.test");
    await user.click(screen.getByRole("button", { name: "Enviar o link" }));

    expect(ask).toHaveBeenCalledWith("alguem@escola.test");
    expect(await screen.findByRole("status")).toHaveTextContent("Se este e-mail tem uma conta");
  });

  it("sem e-mail nao chama a API", async () => {
    const ask = vi.spyOn(api.auth, "requestPasswordReset");
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.click(screen.getByRole("button", { name: "Enviar o link" }));

    expect(ask).not.toHaveBeenCalled();
    expect(screen.getByText("Informe o seu e-mail.")).toBeInTheDocument();
  });

  it("muitas tentativas viram uma frase com o tempo de espera", async () => {
    vi.spyOn(api.auth, "requestPasswordReset").mockResolvedValue({ ok: false, error: { kind: "problem", status: 429, code: "rate_limited", retryAfterSeconds: 90 } });
    const user = userEvent.setup();
    render(<ForgotPasswordForm />);

    await user.type(screen.getByLabelText("Seu e-mail"), "alguem@escola.test");
    await user.click(screen.getByRole("button", { name: "Enviar o link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Muitas tentativas seguidas. Aguarde 2 minutos");
  });
});

describe("Escolher senha nova", () => {
  it("troca a senha com o token da URL e leva para a entrada", async () => {
    const confirm = vi.spyOn(api.auth, "confirmPasswordReset").mockResolvedValue(ok);
    const user = userEvent.setup();
    render(<ResetPasswordForm token={TOKEN} />);

    await user.type(screen.getByLabelText("Senha nova"), NEW);
    await user.type(screen.getByLabelText("Repita a senha nova"), NEW);
    await user.click(screen.getByRole("button", { name: "Salvar a senha nova" }));

    expect(confirm).toHaveBeenCalledWith(TOKEN, NEW);
    expect(await screen.findByRole("status")).toHaveTextContent("Senha alterada");
    expect(screen.getByRole("link", { name: "Ir para a entrada" })).toHaveAttribute("href", "/login");
  });

  it("senha curta ou diferente nao chama a API", async () => {
    const confirm = vi.spyOn(api.auth, "confirmPasswordReset");
    const user = userEvent.setup();
    render(<ResetPasswordForm token={TOKEN} />);

    await user.type(screen.getByLabelText("Senha nova"), "curta");
    await user.click(screen.getByRole("button", { name: "Salvar a senha nova" }));
    expect(screen.getByText("Use pelo menos 12 caracteres.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Senha nova"));
    await user.type(screen.getByLabelText("Senha nova"), NEW);
    await user.type(screen.getByLabelText("Repita a senha nova"), NEW + "x");
    await user.click(screen.getByRole("button", { name: "Salvar a senha nova" }));

    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByText("As senhas não são iguais.")).toBeInTheDocument();
  });

  it("link vencido ou usado mostra uma frase clara e limpa os campos", async () => {
    vi.spyOn(api.auth, "confirmPasswordReset").mockResolvedValue({ ok: false, error: { kind: "problem", status: 400, code: "reset_invalid" } });
    const user = userEvent.setup();
    render(<ResetPasswordForm token={TOKEN} />);

    await user.type(screen.getByLabelText("Senha nova"), NEW);
    await user.type(screen.getByLabelText("Repita a senha nova"), NEW);
    await user.click(screen.getByRole("button", { name: "Salvar a senha nova" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este link não vale mais");
    expect(screen.getByLabelText("Senha nova")).toHaveValue("");
  });
});
