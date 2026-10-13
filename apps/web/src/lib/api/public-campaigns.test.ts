import { describe, expect, it, vi } from "vitest";
import { json, problem } from "@/test-utils/auth-fixtures";
import { CAMPAIGN_ID, ITEM_A, ITEM_B, publicCampaignBody, publicItemBody, publicSummaryBody } from "@/test-utils/campaign-fixtures";
import { RECEIPT_BODY, TOKEN, stateBody } from "@/test-utils/public-fixtures";
import {
  campaignCoverUrl,
  campaignItemImageUrl,
  createOrder,
  getPublicCampaign,
  getPublicCampaigns,
  getReceipt,
  orderBody,
  parsePublicCampaign,
} from "./public";

const KEY = "11111111-1111-4111-8111-111111111111";
const ok = (body: unknown, status = 200) => vi.fn().mockResolvedValue(json(body, status, { "Content-Type": "application/json" }));
const init = (f: ReturnType<typeof vi.fn>) => f.mock.calls[0]![1] as RequestInit & { headers: Record<string, string> };

describe("as campanhas a venda", () => {
  it("lista: GET /public/schools/{slug}/campaigns em camelCase", async () => {
    const f = ok({ campaigns: [publicSummaryBody({ ends_on: "2026-06-30", has_cover: true, cover_version: 2 })] });
    const result = await getPublicCampaigns("demo-aurora", { fetchImpl: f });
    expect(f.mock.calls[0]![0]).toBe("/api/v1/public/schools/demo-aurora/campaigns");
    expect(init(f).method).toBe("GET");
    expect(result).toMatchObject({ ok: true, data: [{ id: CAMPAIGN_ID, title: "Festa Junina", endsOn: "2026-06-30", hasCover: true, coverVersion: 2, itemsCount: 2 }] });
  });

  it("uma lista vazia e uma resposta valida (nenhuma campanha a venda)", async () => {
    expect(await getPublicCampaigns("demo-aurora", { fetchImpl: ok({ campaigns: [] }) })).toEqual({ ok: true, data: [] });
  });

  it("uma campanha: produtos com preco em centavos e limite", async () => {
    const f = ok(publicCampaignBody());
    const result = await getPublicCampaign("demo-aurora", CAMPAIGN_ID, { fetchImpl: f });
    expect(f.mock.calls[0]![0]).toBe(`/api/v1/public/schools/demo-aurora/campaigns/${CAMPAIGN_ID}`);
    expect(result).toMatchObject({
      ok: true,
      data: { items: [{ id: ITEM_A, name: "Cachorro-quente", priceCents: 800, maxPerOrder: 5 }, { id: ITEM_B, name: "Pamonha", priceCents: 650, maxPerOrder: null, description: null }] },
    });
  });

  it("404 e o mesmo para campanha que nao existe, rascunho, encerrada ou de outra escola", async () => {
    expect(await getPublicCampaign("demo-aurora", CAMPAIGN_ID, { fetchImpl: vi.fn().mockResolvedValue(problem("not_found", 404)) })).toMatchObject({ ok: false, error: { status: 404, code: "not_found" } });
  });

  it("recusa resposta mal formada (nada de adivinhar preco)", () => {
    for (const bad of [
      publicCampaignBody({ items: undefined }),
      publicCampaignBody({ title: "" }),
      publicCampaignBody({ items_count: -1 }),
      publicCampaignBody({ items: [publicItemBody({ price_cents: "8" })] }),
      publicCampaignBody({ items: [publicItemBody({ price_cents: 0 })] }),
      publicCampaignBody({ items: [publicItemBody({ price_cents: 8.5 })] }),
      publicCampaignBody({ items: [publicItemBody({ name: "" })] }),
      publicCampaignBody({ items: [publicItemBody({ max_per_order: "5" })] }),
      publicCampaignBody({ items: [publicItemBody({ has_image: "yes" })] }),
    ]) {
      expect(parsePublicCampaign(bad)).toBeNull();
    }
    expect(parsePublicCampaign(publicCampaignBody())).not.toBeNull();
  });

  it("enderecos das imagens: publicos, da mesma origem, com a versao para trocar o cache", () => {
    expect(campaignCoverUrl("demo-aurora", CAMPAIGN_ID, 3)).toBe(`/api/v1/public/schools/demo-aurora/campaigns/${CAMPAIGN_ID}/cover?v=3`);
    expect(campaignItemImageUrl("demo-aurora", CAMPAIGN_ID, ITEM_A, 0)).toBe(`/api/v1/public/schools/demo-aurora/campaigns/${CAMPAIGN_ID}/items/${ITEM_A}/image?v=0`);
  });
});

describe("o pedido", () => {
  it("o corpo leva QUAIS produtos e QUANTOS e so os campos de identificacao preenchidos: nunca um preco nem um total", () => {
    const body = orderBody({ lines: [{ itemId: ITEM_A, quantity: 2 }, { itemId: ITEM_B, quantity: 1 }], identification: { guardianName: "Maria", contributorPhone: "" } });
    expect(body).toEqual({ lines: [{ item_id: ITEM_A, quantity: 2 }, { item_id: ITEM_B, quantity: 1 }], guardian_name: "Maria" });
    expect(JSON.stringify(body)).not.toMatch(/price|amount|total/i);
  });

  it("POST .../campaigns/{id}/orders com a Idempotency-Key no cabecalho, e devolve o token e o Pix", async () => {
    const f = ok({ ...stateBody(), token: TOKEN }, 201);
    const result = await createOrder("demo-aurora", CAMPAIGN_ID, { lines: [{ itemId: ITEM_A, quantity: 2 }], identification: {} }, KEY, { fetchImpl: f, csrfToken: "c".repeat(32) });
    expect(f.mock.calls[0]![0]).toBe(`/api/v1/public/schools/demo-aurora/campaigns/${CAMPAIGN_ID}/orders`);
    expect(init(f).method).toBe("POST");
    expect(init(f).headers["Idempotency-Key"]).toBe(KEY);
    expect(JSON.parse(init(f).body as string)).toEqual({ lines: [{ item_id: ITEM_A, quantity: 2 }] });
    expect(f.mock.calls[0]![0]).not.toContain(KEY); // a chave nunca vai na URL
    expect(result).toMatchObject({ ok: true, data: { token: TOKEN, status: "PENDING_PAYMENT" } });
  });

  it("recusa uma resposta sem token valido", async () => {
    expect((await createOrder("demo-aurora", CAMPAIGN_ID, { lines: [{ itemId: ITEM_A, quantity: 1 }], identification: {} }, KEY, { fetchImpl: ok({ ...stateBody(), token: "curto" }, 201) })).ok).toBe(false);
  });

  it("422 chega com o campo da linha e o codigo; 409 com o code", async () => {
    const refused = vi.fn().mockResolvedValue(
      json({ code: "validation_error", title: "x", errors: [{ field: "lines[0].quantity", code: "over_limit" }] }, 422, { "Content-Type": "application/problem+json" }),
    );
    expect(await createOrder("demo-aurora", CAMPAIGN_ID, { lines: [{ itemId: ITEM_A, quantity: 9 }], identification: {} }, KEY, { fetchImpl: refused })).toMatchObject({
      ok: false,
      error: { status: 422, fields: [{ field: "lines[0].quantity", code: "over_limit" }] },
    });
    expect(await createOrder("demo-aurora", CAMPAIGN_ID, { lines: [{ itemId: ITEM_A, quantity: 1 }], identification: {} }, KEY, { fetchImpl: vi.fn().mockResolvedValue(problem("campaign_changed", 409)) })).toMatchObject({
      error: { status: 409, code: "campaign_changed" },
    });
  });
});

describe("o comprovante do pedido", () => {
  it("lista o que foi comprado, como foi comprado, e o titulo da campanha", async () => {
    const f = ok({ ...RECEIPT_BODY, amount_cents: 2250, campaign_title: "Festa Junina", items: [{ name: "Cachorro-quente", unit_price_cents: 800, quantity: 2 }, { name: "Pamonha", unit_price_cents: 650, quantity: 1 }] });
    const result = await getReceipt("demo-aurora", TOKEN, { fetchImpl: f });
    expect(result).toMatchObject({
      ok: true,
      data: { campaignTitle: "Festa Junina", items: [{ name: "Cachorro-quente", unitPriceCents: 800, quantity: 2 }, { name: "Pamonha", unitPriceCents: 650, quantity: 1 }] },
    });
  });

  it("comprovante antigo (sem os campos novos) continua valido: sem campanha e sem itens", async () => {
    const old: Record<string, unknown> = { ...RECEIPT_BODY };
    delete old.campaign_title;
    delete old.items;
    expect(await getReceipt("demo-aurora", TOKEN, { fetchImpl: ok(old) })).toMatchObject({ ok: true, data: { campaignTitle: null, items: [] } });
  });

  it("recusa itens mal formados", async () => {
    for (const items of [[{ name: "", unit_price_cents: 800, quantity: 1 }], [{ name: "x", unit_price_cents: "8", quantity: 1 }], [{ name: "x", unit_price_cents: 800, quantity: 0 }], "nope"]) {
      expect((await getReceipt("demo-aurora", TOKEN, { fetchImpl: ok({ ...RECEIPT_BODY, items }) })).ok).toBe(false);
    }
  });
});
