import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }) }));

import LoginPage from "./page";

async function html(searchParams: { next?: string; erro?: string } = {}) {
  return renderToStaticMarkup(await LoginPage({ searchParams: Promise.resolve(searchParams) }));
}

afterEach(() => vi.unstubAllEnvs());

describe("/login e a entrada pela Forklin", () => {
  it("desligada (padrao): nada de botao, nada de aviso de Forklin, e a palavra do erro e ignorada", async () => {
    const out = await html({ erro: "org" });
    expect(out).not.toContain("Entrar com Forklin");
    expect(out).not.toContain("Tem conta Forklin");
    expect(out).not.toContain("Organização sem acesso");
    expect(out).toContain("Acessar sua conta");
  });

  it("desligada (padrao): e-mail e senha, esqueci a senha e o aviso do convite, como sempre", async () => {
    const out = await html();
    expect(out).toContain('name="email"');
    expect(out).toContain('name="password"');
    expect(out).toContain("Esqueci minha senha");
    expect(out).toContain("Recebeu um convite?");
  });

  it("ligada: botao para /sso/start e a frase fixa; a entrada e so pela Forklin (sem formulario, sem esqueci a senha, sem convite)", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    const out = await html();
    expect(out).toContain('href="/sso/start"');
    expect(out).toContain("Entrar com Forklin");
    expect(out).toContain("O acesso ao APM Digital vem da sua conta Forklin");
    expect(out).not.toContain('name="email"');
    expect(out).not.toContain('name="password"');
    expect(out).not.toContain("Esqueci minha senha");
    expect(out).not.toContain("Recebeu um convite");
    expect(out).toContain('href="/escola"'); // as familias continuam sem login
  });

  it("ligada: cada palavra do erro mostra a sua frase, e uma desconhecida mostra a generica", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    expect(await html({ erro: "acesso" })).toContain("Você não tem acesso ao APM Digital");
    expect(await html({ erro: "org" })).toContain("Organização sem acesso");
    expect(await html({ erro: "xyz" })).toContain("Entrada indisponível");
  });
});
