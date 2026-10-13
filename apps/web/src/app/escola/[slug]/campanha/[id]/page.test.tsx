import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { json, problem } from "@/test-utils/auth-fixtures";
import { CAMPAIGN_ID, publicCampaignBody } from "@/test-utils/campaign-fixtures";
import { SCHOOL_BODY } from "@/test-utils/public-fixtures";

const upstream = vi.hoisted(() => ({ handler: null as null | ((url: string) => Response | Promise<Response>) }));
vi.mock("@/lib/api/server", () => ({ serverFetch: (input: string) => upstream.handler!(String(input)) }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw Object.assign(new Error("NEXT_NOT_FOUND"), { digest: "NEXT_HTTP_ERROR_FALLBACK;404" });
  },
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

import CampaignPage, { generateMetadata } from "./page";

const JSON_HEADERS = { "Content-Type": "application/json" };
async function html(slug = "demo-aurora", id = CAMPAIGN_ID) {
  return renderToStaticMarkup(await CampaignPage({ params: Promise.resolve({ slug, id }) }));
}

beforeEach(() => {
  upstream.handler = null;
});

describe("/escola/{slug}/campanha/{id} no servidor", () => {
  it("a escola vem do slug e a campanha do id: desenha os produtos com o preco da API", async () => {
    const seen: string[] = [];
    upstream.handler = (url) => {
      seen.push(url);
      return url.endsWith(`/campaigns/${CAMPAIGN_ID}`) ? json(publicCampaignBody(), 200, JSON_HEADERS) : json(SCHOOL_BODY, 200, JSON_HEADERS);
    };

    const out = await html();

    expect([...seen].sort()).toEqual(["/api/v1/public/schools/demo-aurora", `/api/v1/public/schools/demo-aurora/campaigns/${CAMPAIGN_ID}`]);
    expect(out).toContain("Festa Junina");
    expect(out).toContain("Escolha os produtos");
    expect(out).toContain("Cachorro-quente");
    expect(out).toMatch(/R\$\s8,00/);
    expect(out).toMatch(/R\$\s6,50/);
    expect(out).toContain("No máximo 5 por pedido.");
    expect((await generateMetadata({ params: Promise.resolve({ slug: "demo-aurora", id: CAMPAIGN_ID }) })).title).toBe("Festa Junina");
  });

  it("campanha que nao existe, rascunho, encerrada ou de outra escola: o mesmo 404 do site", async () => {
    upstream.handler = (url) => (url.includes("/campaigns/") ? problem("not_found", 404) : json(SCHOOL_BODY, 200, JSON_HEADERS));
    await expect(html()).rejects.toMatchObject({ digest: expect.stringContaining("404") });
    expect((await generateMetadata({ params: Promise.resolve({ slug: "demo-aurora", id: CAMPAIGN_ID }) })).title).toBe("Campanha não encontrada");
  });

  it("slug ou id mal formados: 404 sem chamar a API", async () => {
    const handler = vi.fn();
    upstream.handler = handler;
    await expect(html("../etc")).rejects.toMatchObject({ digest: expect.stringContaining("404") });
    await expect(html("demo-aurora", "nao-e-um-uuid")).rejects.toMatchObject({ digest: expect.stringContaining("404") });
    expect(handler).not.toHaveBeenCalled();
  });

  it("429 e API fora do ar: tela amigavel, nunca texto do servidor", async () => {
    upstream.handler = () => problem("rate_limited", 429, {}, { "Retry-After": "90" });
    const limited = await html();
    expect(limited).toContain("Muitos acessos agora");
    expect(limited).toContain("2 minutos");
    upstream.handler = () => Promise.reject(new TypeError("fetch failed"));
    const down = await html();
    expect(down).toContain("Não foi possível abrir esta página");
    expect(down).toContain("Nada foi cobrado");
  });
});
