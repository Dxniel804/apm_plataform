import type { CampaignDetail, CampaignItem, CampaignSummary, PublicCampaign, PublicCampaignItem, PublicCampaignSummary } from "@/lib/api/types";

/** Dados FALSOS para os testes das campanhas. snake_case = formato da API; os objetos em camelCase sao o que o site usa. */
export const CAMPAIGN_ID = "c1c1c1c1-1111-4111-8111-111111111111";
export const ITEM_A = "a1a1a1a1-1111-4111-8111-111111111111";
export const ITEM_B = "b2b2b2b2-2222-4222-8222-222222222222";

export function itemBody(overrides: Record<string, unknown> = {}) {
  return {
    id: ITEM_A,
    name: "Cachorro-quente",
    description: "Pão, salsicha e molho da casa.",
    price_cents: 800,
    unit_cost_cents: null,
    max_per_order: 5,
    position: 0,
    is_active: true,
    has_image: false,
    image_version: 0,
    ...overrides,
  };
}

export function summaryBody(overrides: Record<string, unknown> = {}) {
  return {
    id: CAMPAIGN_ID,
    title: "Festa Junina",
    status: "DRAFT",
    starts_on: null,
    ends_on: null,
    has_cover: false,
    items_count: 2,
    active_items_count: 2,
    paid_orders_count: 0,
    paid_cents: 0,
    created_at: "2026-10-06T13:41:42Z",
    updated_at: "2026-10-06T13:41:42Z",
    ...overrides,
  };
}

export function detailBody(overrides: Record<string, unknown> = {}) {
  return {
    ...summaryBody(),
    description: "Barracas, jogos e a camiseta da turma.",
    cover_version: 0,
    ask_student_class: false,
    items: [itemBody(), itemBody({ id: ITEM_B, name: "Pamonha", description: null, price_cents: 650, max_per_order: null, position: 1 })],
    ...overrides,
  };
}

export function item(overrides: Partial<CampaignItem> = {}): CampaignItem {
  return { id: ITEM_A, name: "Cachorro-quente", description: "Pão, salsicha e molho da casa.", priceCents: 800, unitCostCents: null, maxPerOrder: 5, position: 0, isActive: true, hasImage: false, imageVersion: 0, ...overrides };
}

export function summary(overrides: Partial<CampaignSummary> = {}): CampaignSummary {
  return {
    id: CAMPAIGN_ID, title: "Festa Junina", status: "DRAFT", startsOn: null, endsOn: null, hasCover: false, itemsCount: 2, activeItemsCount: 2,
    paidOrdersCount: 0, paidCents: 0, createdAt: "2026-10-06T13:41:42Z", updatedAt: "2026-10-06T13:41:42Z", ...overrides,
  };
}

export function detail(overrides: Partial<CampaignDetail> = {}): CampaignDetail {
  return {
    ...summary(),
    description: "Barracas, jogos e a camiseta da turma.",
    coverVersion: 0,
    askStudentClass: false,
    items: [item(), item({ id: ITEM_B, name: "Pamonha", description: null, priceCents: 650, maxPerOrder: null, position: 1 })],
    ...overrides,
  };
}

// --- o que a familia ve ----------------------------------------------------------------------------

export function publicItemBody(overrides: Record<string, unknown> = {}) {
  return {
    id: ITEM_A,
    name: "Cachorro-quente",
    description: "Pão, salsicha e molho da casa.",
    price_cents: 800,
    max_per_order: 5,
    has_image: false,
    image_version: 0,
    ...overrides,
  };
}

export function publicSummaryBody(overrides: Record<string, unknown> = {}) {
  return {
    id: CAMPAIGN_ID,
    title: "Festa Junina",
    description: "Barracas, jogos e a camiseta da turma.",
    ends_on: null,
    has_cover: false,
    cover_version: 0,
    items_count: 2,
    ask_student_class: false,
    ...overrides,
  };
}

export function publicCampaignBody(overrides: Record<string, unknown> = {}) {
  return {
    ...publicSummaryBody(),
    items: [publicItemBody(), publicItemBody({ id: ITEM_B, name: "Pamonha", description: null, price_cents: 650, max_per_order: null })],
    ...overrides,
  };
}

export function publicItem(overrides: Partial<PublicCampaignItem> = {}): PublicCampaignItem {
  return { id: ITEM_A, name: "Cachorro-quente", description: "Pão, salsicha e molho da casa.", priceCents: 800, maxPerOrder: 5, hasImage: false, imageVersion: 0, ...overrides };
}

export function publicSummary(overrides: Partial<PublicCampaignSummary> = {}): PublicCampaignSummary {
  return { id: CAMPAIGN_ID, title: "Festa Junina", description: "Barracas, jogos e a camiseta da turma.", endsOn: null, hasCover: false, coverVersion: 0, itemsCount: 2, askStudentClass: false, ...overrides };
}

export function publicCampaign(overrides: Partial<PublicCampaign> = {}): PublicCampaign {
  return {
    ...publicSummary(),
    items: [publicItem(), publicItem({ id: ITEM_B, name: "Pamonha", description: null, priceCents: 650, maxPerOrder: null })],
    ...overrides,
  };
}

// --- o painel da campanha, os pedidos e a entrega (0014) ------------------------------------------

export const ORDER_1 = "d1d1d1d1-1111-4111-8111-111111111111";
export const ORDER_2 = "d2d2d2d2-2222-4222-8222-222222222222";
export const ORDER_3 = "d3d3d3d3-3333-4333-8333-333333333333";

export function dashboardBody(overrides: Record<string, unknown> = {}) {
  return {
    campaign_id: CAMPAIGN_ID,
    title: "Festa Junina",
    status: "ACTIVE",
    paid_orders_count: 2,
    pending_orders_count: 1,
    cancelled_orders_count: 0,
    collected_cents: 3050,
    units_sold: 4,
    cost_cents: 1100,
    cost_complete: true,
    profit_cents: 1950,
    delivered_orders_count: 1,
    to_deliver_orders_count: 1,
    items: [
      { item_id: ITEM_A, name: "Cachorro-quente", units_sold: 3, revenue_cents: 2400, cost_cents: 900, cost_known: true },
      { item_id: ITEM_B, name: "Pamonha", units_sold: 1, revenue_cents: 650, cost_cents: 200, cost_known: true },
    ],
    ...overrides,
  };
}

export function orderBody(overrides: Record<string, unknown> = {}) {
  return {
    order_id: ORDER_1,
    reference_code: 42,
    created_at: "2026-10-14T13:00:00Z",
    guardian_name: "Maria",
    student_name: "Ana",
    class_name: "3A",
    amount_cents: 2250,
    payment_status: "PAID",
    delivery_status: "PENDING",
    delivery_changed_at: null,
    lines: [
      { item_name: "Cachorro-quente", quantity: 2, unit_price_cents: 800 },
      { item_name: "Pamonha", quantity: 1, unit_price_cents: 650 },
    ],
    ...overrides,
  };
}

export function orderPageBody(items: unknown[] = [orderBody()], overrides: Record<string, unknown> = {}) {
  return { items, total: items.length, limit: 25, offset: 0, ...overrides };
}
