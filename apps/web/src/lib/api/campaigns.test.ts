import { describe, expect, it, vi } from "vitest";
import { CAMPAIGN_ID, ITEM_A, detailBody, itemBody, summaryBody } from "@/test-utils/campaign-fixtures";
import { json, problem } from "@/test-utils/auth-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import {
  activateCampaign, addCampaignItem, clearCampaignImage, createCampaign, downloadCampaignImage, endCampaign, getCampaign, listCampaigns,
  parseCampaignDetail, setCampaignImage, updateCampaign, updateCampaignItem,
} from "./campaigns";

const ok = (body: unknown, status = 200) => vi.fn().mockResolvedValue(json(body, status, { "Content-Type": "application/json" }));
const csrf = "c".repeat(32);
type Init = RequestInit & { headers: Record<string, string> };
const init = (f: ReturnType<typeof vi.fn>): Init => f.mock.calls[0]![1] as Init;
const url = (f: ReturnType<typeof vi.fn>) => f.mock.calls[0]![0] as string;
const sent = (f: ReturnType<typeof vi.fn>) => JSON.parse(init(f).body as string) as Record<string, unknown>;
const base = `/api/v1/schools/${SCHOOL_ID}/campaigns`;

describe("leitura", () => {
  it("lista as campanhas com as contagens, em camelCase, e filtra por situacao", async () => {
    const f = ok({ items: [summaryBody({ status: "ACTIVE", paid_orders_count: 3, paid_cents: 5400 })] });
    const result = await listCampaigns(SCHOOL_ID, { status: "ACTIVE" }, { fetchImpl: f });
    expect(url(f)).toBe(`${base}?status=ACTIVE`);
    expect(result).toMatchObject({ ok: true, data: [{ id: CAMPAIGN_ID, status: "ACTIVE", paidOrdersCount: 3, paidCents: 5400, hasCover: false, startsOn: null }] });
  });

  it("detalhe: texto, capa, produtos com preco em centavos e limite", async () => {
    const f = ok(detailBody({ cover_version: 2, has_cover: true }));
    const result = await getCampaign(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: f });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}`);
    expect(result).toMatchObject({
      ok: true,
      data: { coverVersion: 2, hasCover: true, items: [{ name: "Cachorro-quente", priceCents: 800, maxPerOrder: 5, isActive: true }, { name: "Pamonha", maxPerOrder: null, description: null }] },
    });
  });

  it("recusa situacao, preco, contagem ou produto mal formados (nada de adivinhar)", () => {
    for (const bad of [
      detailBody({ status: "LIVE" }), detailBody({ title: "" }), detailBody({ items_count: 1.5 }), detailBody({ paid_cents: "9" }), detailBody({ items: undefined }),
      detailBody({ items: [itemBody({ price_cents: "8" })] }), detailBody({ items: [itemBody({ is_active: "yes" })] }), detailBody({ items: [itemBody({ name: "" })] }),
      detailBody({ cover_version: -0.5 }),
    ]) {
      expect(parseCampaignDetail(bad)).toBeNull();
    }
    expect(parseCampaignDetail(detailBody())).not.toBeNull();
  });

  it("403 e 404 viram erros com code", async () => {
    expect(await getCampaign(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: vi.fn().mockResolvedValue(problem("not_found", 404)) })).toMatchObject({ error: { status: 404, code: "not_found" } });
    expect(await listCampaigns(SCHOOL_ID, {}, { fetchImpl: vi.fn().mockResolvedValue(problem("permission_denied", 403)) })).toMatchObject({ error: { status: 403 } });
  });
});

describe("escrita", () => {
  it("criar: POST so com o que foi preenchido (nasce rascunho)", async () => {
    const f = ok(detailBody(), 201);
    const result = await createCampaign(SCHOOL_ID, { title: "Festa", description: "", startsOn: "2026-06-01" }, { fetchImpl: f, csrfToken: csrf });
    expect(url(f)).toBe(base);
    expect(init(f).method).toBe("POST");
    expect(init(f).headers["X-CSRF-Token"]).toBe(csrf);
    expect(sent(f)).toEqual({ title: "Festa", starts_on: "2026-06-01" });
    expect(result.ok).toBe(true);
  });

  it("editar: PATCH so com o que mudou; null apaga um campo opcional", async () => {
    const f = ok(detailBody());
    await updateCampaign(SCHOOL_ID, CAMPAIGN_ID, { title: "Nova", description: null, endsOn: null }, { fetchImpl: f, csrfToken: csrf });
    expect(init(f).method).toBe("PATCH");
    expect(sent(f)).toEqual({ title: "Nova", description: null, ends_on: null });
  });

  it("por a venda e encerrar: POST sem corpo", async () => {
    const a = ok(detailBody({ status: "ACTIVE" }));
    await activateCampaign(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: a, csrfToken: csrf });
    expect(url(a)).toBe(`${base}/${CAMPAIGN_ID}/activate`);
    expect(init(a).method).toBe("POST");
    const e = ok(detailBody({ status: "ENDED" }));
    expect(await endCampaign(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: e, csrfToken: csrf })).toMatchObject({ ok: true, data: { status: "ENDED" } });
    expect(url(e)).toBe(`${base}/${CAMPAIGN_ID}/end`);
  });

  it("produto: o preco vai em centavos e o limite so quando existe", async () => {
    const f = ok(detailBody(), 201);
    await addCampaignItem(SCHOOL_ID, CAMPAIGN_ID, { name: "Pamonha", priceCents: 650, maxPerOrder: null }, { fetchImpl: f, csrfToken: csrf });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/items`);
    expect(sent(f)).toEqual({ name: "Pamonha", price_cents: 650 });
    const g = ok(detailBody());
    await updateCampaignItem(SCHOOL_ID, CAMPAIGN_ID, ITEM_A, { priceCents: 900, maxPerOrder: null, isActive: false }, { fetchImpl: g, csrfToken: csrf });
    expect(url(g)).toBe(`${base}/${CAMPAIGN_ID}/items/${ITEM_A}`);
    expect(init(g).method).toBe("PATCH");
    expect(sent(g)).toEqual({ price_cents: 900, max_per_order: null, is_active: false });
  });

  it("imagem: PUT multipart so com o arquivo; remover e DELETE; ver e GET com a sessao", async () => {
    const f = ok(detailBody({ has_cover: true }));
    const file = new File([new Uint8Array(10)], "capa.png", { type: "image/png" });
    await setCampaignImage(SCHOOL_ID, CAMPAIGN_ID, file, undefined, { fetchImpl: f, csrfToken: csrf });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/image`);
    expect(init(f).method).toBe("PUT");
    expect(init(f).body).toBeInstanceOf(FormData);
    expect((init(f).body as FormData).get("file")).toBeInstanceOf(File);
    expect(init(f).headers["Content-Type"]).toBeUndefined(); // o navegador poe o boundary

    const g = ok(detailBody());
    await setCampaignImage(SCHOOL_ID, CAMPAIGN_ID, file, ITEM_A, { fetchImpl: g, csrfToken: csrf });
    expect(url(g)).toBe(`${base}/${CAMPAIGN_ID}/items/${ITEM_A}/image`);

    const d = ok(detailBody());
    await clearCampaignImage(SCHOOL_ID, CAMPAIGN_ID, ITEM_A, { fetchImpl: d, csrfToken: csrf });
    expect(init(d).method).toBe("DELETE");

    const blob = vi.fn().mockResolvedValue(new Response("x", { status: 200, headers: { "Content-Type": "image/png" } }));
    const shown = await downloadCampaignImage(SCHOOL_ID, CAMPAIGN_ID, undefined, { fetchImpl: blob });
    expect(url(blob)).toBe(`${base}/${CAMPAIGN_ID}/image`);
    expect(shown.ok).toBe(true);
  });

  it("409 e 422 chegam com o code e o campo", async () => {
    const f = vi.fn().mockResolvedValue(problem("campaign_needs_a_product", 409));
    expect(await activateCampaign(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: f, csrfToken: csrf })).toMatchObject({ ok: false, error: { status: 409, code: "campaign_needs_a_product" } });
  });
});
