import { afterEach, describe, expect, it, vi } from "vitest";
import { describeSsoError, forklinEnabled, proxySso } from "./forklin";

afterEach(() => vi.unstubAllEnvs());

describe("forklinEnabled", () => {
  it("so liga com a palavra true (qualquer caixa); o resto, inclusive vazio, e desligado", () => {
    expect(forklinEnabled("true")).toBe(true);
    expect(forklinEnabled(" TRUE ")).toBe(true);
    for (const off of [undefined, "", "false", "1", "yes", "tru"]) expect(forklinEnabled(off)).toBe(false);
  });
});

describe("describeSsoError", () => {
  it("cada palavra da API tem a sua frase; sem palavra nao ha aviso; palavra desconhecida vira a frase generica", () => {
    expect(describeSsoError(undefined)).toBeNull();
    expect(describeSsoError("org")?.title).toBe("Organização sem acesso");
    expect(describeSsoError("cargo")?.title).toBe("Cargo não reconhecido");
    expect(describeSsoError(["expirado", "org"])?.title).toBe("Entrada expirada");
    expect(describeSsoError("qualquer-coisa")?.title).toBe("Entrada indisponível");
    expect(describeSsoError("__proto__")?.title).toBe("Entrada indisponível");
  });
});

describe("proxySso", () => {
  const request = (path: string, headers: Record<string, string> = {}) =>
    new Request(`http://localhost:3101${path}`, { headers });

  it("desligado: 404 e nem chama a API", async () => {
    const fetchImpl = vi.fn();
    const response = await proxySso(request("/sso/start"), "start", fetchImpl as unknown as typeof fetch);
    expect(response.status).toBe(404);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("ligado: repassa o cookie e a query, sem seguir o redirecionamento, e devolve Location e todos os Set-Cookie", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    vi.stubEnv("API_PROXY_URL", "http://127.0.0.1:9999");
    const upstream = new Response(null, { status: 302, headers: { Location: "/painel", "Set-Cookie": "a=1; Path=/" } });
    upstream.headers.append("Set-Cookie", "b=2; Path=/");
    const fetchImpl = vi.fn().mockResolvedValue(upstream);
    const response = await proxySso(
      request("/sso/callback?code=abc&state=xyz", { cookie: "apm_sso_state=xyz", "user-agent": "UA" }),
      "callback",
      fetchImpl as unknown as typeof fetch,
    );
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:9999/api/v1/forklin/sso/callback?code=abc&state=xyz");
    expect(init.redirect).toBe("manual");
    expect((init.headers as Record<string, string>).Cookie).toBe("apm_sso_state=xyz");
    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/painel");
    expect(response.headers.getSetCookie()).toEqual(["a=1; Path=/", "b=2; Path=/"]);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });

  it("o start nao leva a query do navegador a API", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    const fetchImpl = vi.fn().mockResolvedValue(new Response(null, { status: 302, headers: { Location: "http://app/x" } }));
    await proxySso(request("/sso/start?code=roubado"), "start", fetchImpl as unknown as typeof fetch);
    expect((fetchImpl.mock.calls[0] as [string])[0]).toMatch(/\/api\/v1\/forklin\/sso\/start$/);
  });

  it("API fora do ar: volta ao login com o aviso, nunca um erro 500", async () => {
    vi.stubEnv("FORKLIN_CORE_ENABLED", "true");
    const fetchImpl = vi.fn().mockRejectedValue(new Error("boom"));
    const response = await proxySso(request("/sso/callback?code=a"), "callback", fetchImpl as unknown as typeof fetch);
    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("/login?erro=indisponivel");
  });
});
