import { describe, expect, it, vi } from "vitest";
import { CAMPAIGN_ID, ITEM_A, ORDER_1, ORDER_2, dashboardBody, detailBody, itemBody, orderBody, orderPageBody, summaryBody } from "@/test-utils/campaign-fixtures";
import { json, problem } from "@/test-utils/auth-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import {
  activateCampaign, addCampaignItem, changeCampaignDelivery, clearCampaignImage, createCampaign, downloadCampaignImage, downloadCampaignReport, endCampaign,
  getCampaign, getCampaignDashboard, listCampaignOrders, listCampaigns, parseCampaignDetail, setCampaignImage, updateCampaign, updateCampaignItem,
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

describe("painel da campanha, pedidos e entrega", () => {
  it("dashboard: arrecadado, custo, lucro, entregas e vendidos por produto, em camelCase", async () => {
    const f = ok(dashboardBody());
    const result = await getCampaignDashboard(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: f });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/dashboard`);
    expect(result).toMatchObject({
      ok: true,
      data: {
        collectedCents: 3050, costCents: 1100, costComplete: true, profitCents: 1950, deliveredOrdersCount: 1, toDeliverOrdersCount: 1,
        items: [{ name: "Cachorro-quente", unitsSold: 3, revenueCents: 2400, costCents: 900, costKnown: true }, { name: "Pamonha" }],
      },
    });
  });

  it("dashboard sem lucro: o custo incompleto vem como null (a tela diz 'custo nao informado')", async () => {
    const result = await getCampaignDashboard(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: ok(dashboardBody({ cost_complete: false, profit_cents: null, items: [{ item_id: ITEM_A, name: "Pamonha", units_sold: 1, revenue_cents: 650, cost_cents: null, cost_known: false }] })) });
    expect(result).toMatchObject({ ok: true, data: { costComplete: false, profitCents: null, items: [{ costCents: null, costKnown: false }] } });
  });

  it("recusa numero, situacao ou produto mal formados no dashboard", async () => {
    for (const bad of [dashboardBody({ collected_cents: "3" }), dashboardBody({ status: "LIVE" }), dashboardBody({ cost_complete: "sim" }), dashboardBody({ items: [{ item_id: ITEM_A }] }), dashboardBody({ paid_orders_count: 1.5 })]) {
      const result = await getCampaignDashboard(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: ok(bad) });
      expect(result.ok).toBe(false);
    }
  });

  it("pedidos: filtros e busca vao na URL, a pagina volta em camelCase", async () => {
    const f = ok(orderPageBody([orderBody(), orderBody({ order_id: ORDER_2, payment_status: "PENDING", delivery_status: null })], { total: 2 }));
    const result = await listCampaignOrders(SCHOOL_ID, CAMPAIGN_ID, { payment: "PAID", delivery: "PENDING", search: "  ana ", limit: 25, offset: 50 }, { fetchImpl: f });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/orders?payment=PAID&delivery=PENDING&search=ana&limit=25&offset=50`);
    expect(result).toMatchObject({
      ok: true,
      data: {
        total: 2,
        items: [
          { orderId: ORDER_1, referenceCode: 42, studentName: "Ana", className: "3A", paymentStatus: "PAID", deliveryStatus: "PENDING", lines: [{ itemName: "Cachorro-quente", quantity: 2, unitPriceCents: 800 }, { itemName: "Pamonha" }] },
          { paymentStatus: "PENDING", deliveryStatus: null },
        ],
      },
    });
  });

  it("pedidos sem filtro: sem query; e um pagamento ou entrega desconhecidos sao recusados", async () => {
    const f = ok(orderPageBody());
    await listCampaignOrders(SCHOOL_ID, CAMPAIGN_ID, {}, { fetchImpl: f });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/orders`);
    for (const bad of [orderBody({ payment_status: "REFUNDED" }), orderBody({ delivery_status: "LOST" }), orderBody({ amount_cents: "9" }), orderBody({ lines: [{ item_name: "", quantity: 1, unit_price_cents: 1 }] })]) {
      expect((await listCampaignOrders(SCHOOL_ID, CAMPAIGN_ID, {}, { fetchImpl: ok(orderPageBody([bad])) })).ok).toBe(false);
    }
  });

  it("entrega: POST com os ids e a escolha, e o resultado em tres numeros", async () => {
    const f = ok({ changed: 1, unchanged: 1, skipped: 0 });
    const result = await changeCampaignDelivery(SCHOOL_ID, CAMPAIGN_ID, [ORDER_1, ORDER_2], true, { fetchImpl: f, csrfToken: csrf });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/orders/delivery`);
    expect(init(f).method).toBe("POST");
    expect(init(f).headers["X-CSRF-Token"]).toBe(csrf);
    expect(sent(f)).toEqual({ order_ids: [ORDER_1, ORDER_2], delivered: true });
    expect(result).toMatchObject({ ok: true, data: { changed: 1, unchanged: 1, skipped: 0 } });
    expect((await changeCampaignDelivery(SCHOOL_ID, CAMPAIGN_ID, [ORDER_1], false, { fetchImpl: ok({ changed: "1" }), csrfToken: csrf })).ok).toBe(false);
  });

  it("o PDF da campanha vem da API com a sessao", async () => {
    const f = vi.fn().mockResolvedValue(new Response("%PDF-1.4", { status: 200, headers: { "Content-Type": "application/pdf" } }));
    const result = await downloadCampaignReport(SCHOOL_ID, CAMPAIGN_ID, { fetchImpl: f });
    expect(url(f)).toBe(`${base}/${CAMPAIGN_ID}/report.pdf`);
    expect(result).toMatchObject({ ok: true, data: { contentType: "application/pdf" } });
  });

  it("custo do produto e o aluno e turma da campanha vao no corpo; custo nulo apaga", async () => {
    const created = ok(detailBody(), 201);
    await createCampaign(SCHOOL_ID, { title: "Festa", askStudentClass: false }, { fetchImpl: created, csrfToken: csrf });
    expect(sent(created)).toEqual({ title: "Festa", ask_student_class: false });
    const added = ok(detailBody(), 201);
    await addCampaignItem(SCHOOL_ID, CAMPAIGN_ID, { name: "Bolo", priceCents: 900, unitCostCents: 0 }, { fetchImpl: added, csrfToken: csrf });
    expect(sent(added)).toEqual({ name: "Bolo", price_cents: 900, unit_cost_cents: 0 });
    const cleared = ok(detailBody());
    await updateCampaignItem(SCHOOL_ID, CAMPAIGN_ID, ITEM_A, { unitCostCents: null }, { fetchImpl: cleared, csrfToken: csrf });
    expect(sent(cleared)).toEqual({ unit_cost_cents: null });
    const patched = ok(detailBody());
    await updateCampaign(SCHOOL_ID, CAMPAIGN_ID, { askStudentClass: true }, { fetchImpl: patched, csrfToken: csrf });
    expect(sent(patched)).toEqual({ ask_student_class: true });
  });

  it("o produto traz o custo e a campanha traz o aluno e turma", () => {
    const parsed = parseCampaignDetail(detailBody({ ask_student_class: true, items: [itemBody({ unit_cost_cents: 300 })] }));
    expect(parsed).toMatchObject({ askStudentClass: true, items: [{ unitCostCents: 300 }] });
    expect(parseCampaignDetail(detailBody({ ask_student_class: "sim" }))).toBeNull();
    expect(parseCampaignDetail(detailBody({ items: [itemBody({ unit_cost_cents: "3" })] }))).toBeNull();
  });
});
