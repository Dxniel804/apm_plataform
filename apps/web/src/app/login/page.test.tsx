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

  it("ligada: botao para /sso/start e a frase fixa sobre a senha da Forklin", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    const out = await html();
    expect(out).toContain('href="/sso/start"');
    expect(out).toContain("Entrar com Forklin");
    expect(out).toContain("a senha da Forklin não vale neste formulário");
  });

  it("ligada: cada palavra do erro mostra a sua frase, e uma desconhecida mostra a generica", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    expect(await html({ erro: "acesso" })).toContain("Você não tem acesso ao APM Digital");
    expect(await html({ erro: "org" })).toContain("Organização sem acesso");
    expect(await html({ erro: "xyz" })).toContain("Entrada indisponível");
  });
});
