import { apiBlob, apiGet, apiSend, apiUpload, type BlobPayload, type RequestOptions, type SendOptions } from "./client";
import type {
  ApiResult,
  CampaignBuyer,
  CampaignBuyerList,
  CampaignDashboard,
  CampaignDetail,
  CampaignInput,
  CampaignItem,
  CampaignItemInput,
  CampaignOrder,
  CampaignOrderPage,
  CampaignStatus,
  CampaignSummary,
  DeliveryResult,
  OrderDeliveryStatus,
  OrderFilters,
  OrderPaymentStatus,
  SoldItem,
} from "./types";

/**
 * Campanhas REAIS da gestao (docs/campaigns.md). A escola do caminho e o `school.id` do vinculo ativo; a API
 * ainda confere contra a sessao. O site nunca decide estado nem preco de pedido: mostra o que a API devolve.
 * Toda escrita devolve a campanha inteira, com os produtos.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const int = (v: unknown): number | null => (typeof v === "number" && Number.isSafeInteger(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const optStr = (v: unknown): string | null | undefined => (v === null || v === undefined ? null : typeof v === "string" ? v : undefined);
const optInt = (v: unknown): number | null | undefined => (v === null || v === undefined ? null : int(v) ?? undefined);

export const CAMPAIGN_STATUSES: readonly CampaignStatus[] = ["DRAFT", "ACTIVE", "ENDED"];

function parseItem(v: unknown): CampaignItem | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const name = str(v.name);
  const description = optStr(v.description);
  const priceCents = int(v.price_cents);
  const unitCostCents = optInt(v.unit_cost_cents);
  const maxPerOrder = optInt(v.max_per_order);
  const position = int(v.position);
  const imageVersion = int(v.image_version);
  if (!id || !name || description === undefined || priceCents === null || priceCents < 0 || unitCostCents === undefined || maxPerOrder === undefined) return null;
  if (position === null || imageVersion === null || typeof v.is_active !== "boolean" || typeof v.has_image !== "boolean") return null;
  return { id, name, description, priceCents, unitCostCents, maxPerOrder, position, isActive: v.is_active, hasImage: v.has_image, imageVersion };
}

function parseSummary(v: unknown): CampaignSummary | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const title = str(v.title);
  const status = typeof v.status === "string" && (CAMPAIGN_STATUSES as readonly string[]).includes(v.status) ? (v.status as CampaignStatus) : null;
  const startsOn = optStr(v.starts_on);
  const endsOn = optStr(v.ends_on);
  const itemsCount = int(v.items_count);
  const activeItemsCount = int(v.active_items_count);
  const paidOrdersCount = int(v.paid_orders_count);
  const paidCents = int(v.paid_cents);
  const createdAt = str(v.created_at);
  const updatedAt = str(v.updated_at);
  if (!id || !title || !status || startsOn === undefined || endsOn === undefined || typeof v.has_cover !== "boolean") return null;
  if (itemsCount === null || activeItemsCount === null || paidOrdersCount === null || paidCents === null || !createdAt || !updatedAt) return null;
  return { id, title, status, startsOn, endsOn, hasCover: v.has_cover, itemsCount, activeItemsCount, paidOrdersCount, paidCents, createdAt, updatedAt };
}

export function parseCampaignDetail(v: unknown): CampaignDetail | null {
  const base = parseSummary(v);
  if (!base || !isRecord(v) || !Array.isArray(v.items)) return null;
  const items: CampaignItem[] = [];
  for (const raw of v.items) {
    const item = parseItem(raw);
    if (!item) return null;
    items.push(item);
  }
  const description = optStr(v.description);
  const coverVersion = int(v.cover_version);
  if (description === undefined || coverVersion === null || typeof v.ask_student_class !== "boolean") return null;
  return { ...base, description, coverVersion, askStudentClass: v.ask_student_class, items };
}

function parseList(body: unknown): CampaignSummary[] | null {
  if (!isRecord(body) || !Array.isArray(body.items)) return null;
  const items: CampaignSummary[] = [];
  for (const raw of body.items) {
    const item = parseSummary(raw);
    if (!item) return null;
    items.push(item);
  }
  return items;
}

const enc = encodeURIComponent;
const base = (schoolId: string) => `/api/v1/schools/${enc(schoolId)}/campaigns`;
const detailOk = (body: unknown, status: number) => (status === 200 || status === 201 ? parseCampaignDetail(body) : null);

/** GET .../campaigns: as da escola, as que estao a venda primeiro. */
export function listCampaigns(schoolId: string, params: { status?: CampaignStatus } = {}, options?: RequestOptions): Promise<ApiResult<CampaignSummary[]>> {
  const query = params.status ? `?status=${enc(params.status)}` : "";
  return apiGet(`${base(schoolId)}${query}`, (body, status) => (status === 200 ? parseList(body) : null), options);
}

export function getCampaign(schoolId: string, campaignId: string, options?: RequestOptions): Promise<ApiResult<CampaignDetail>> {
  return apiGet(`${base(schoolId)}/${enc(campaignId)}`, detailOk, options);
}

/** POST .../campaigns: nasce como RASCUNHO (nada a venda). */
export function createCampaign(schoolId: string, input: CampaignInput, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  const body: Record<string, unknown> = { title: input.title };
  if (input.description) body.description = input.description;
  if (input.startsOn) body.starts_on = input.startsOn;
  if (input.endsOn) body.ends_on = input.endsOn;
  if (input.askStudentClass !== undefined) body.ask_student_class = input.askStudentClass;
  return apiSend("POST", base(schoolId), body, detailOk, options);
}

/** PATCH: so o que foi enviado muda; `null` apaga um campo opcional (texto, datas). */
export function updateCampaign(schoolId: string, campaignId: string, changes: Partial<CampaignInput>, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  const body: Record<string, unknown> = {};
  if (changes.title !== undefined) body.title = changes.title;
  if (changes.description !== undefined) body.description = changes.description;
  if (changes.startsOn !== undefined) body.starts_on = changes.startsOn;
  if (changes.endsOn !== undefined) body.ends_on = changes.endsOn;
  if (changes.askStudentClass !== undefined) body.ask_student_class = changes.askStudentClass;
  return apiSend("PATCH", `${base(schoolId)}/${enc(campaignId)}`, body, detailOk, options);
}

export const activateCampaign = (schoolId: string, campaignId: string, options?: SendOptions) =>
  apiSend("POST", `${base(schoolId)}/${enc(campaignId)}/activate`, undefined, detailOk, options);
export const endCampaign = (schoolId: string, campaignId: string, options?: SendOptions) =>
  apiSend("POST", `${base(schoolId)}/${enc(campaignId)}/end`, undefined, detailOk, options);

export function addCampaignItem(schoolId: string, campaignId: string, input: CampaignItemInput, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  const body: Record<string, unknown> = { name: input.name, price_cents: input.priceCents };
  if (input.description) body.description = input.description;
  if (input.unitCostCents !== undefined && input.unitCostCents !== null) body.unit_cost_cents = input.unitCostCents;
  if (input.maxPerOrder) body.max_per_order = input.maxPerOrder;
  if (input.position !== undefined) body.position = input.position;
  return apiSend("POST", `${base(schoolId)}/${enc(campaignId)}/items`, body, detailOk, options);
}

/** PATCH de um produto. Um preco novo nunca toca num pedido ja feito (o pedido guarda uma copia). */
export function updateCampaignItem(
  schoolId: string,
  campaignId: string,
  itemId: string,
  changes: Partial<CampaignItemInput> & { isActive?: boolean },
  options?: SendOptions,
): Promise<ApiResult<CampaignDetail>> {
  const body: Record<string, unknown> = {};
  if (changes.name !== undefined) body.name = changes.name;
  if (changes.description !== undefined) body.description = changes.description;
  if (changes.priceCents !== undefined) body.price_cents = changes.priceCents;
  if (changes.unitCostCents !== undefined) body.unit_cost_cents = changes.unitCostCents;
  if (changes.maxPerOrder !== undefined) body.max_per_order = changes.maxPerOrder;
  if (changes.position !== undefined) body.position = changes.position;
  if (changes.isActive !== undefined) body.is_active = changes.isActive;
  return apiSend("PATCH", `${base(schoolId)}/${enc(campaignId)}/items/${enc(itemId)}`, body, detailOk, options);
}

const imagePath = (schoolId: string, campaignId: string, itemId?: string) =>
  itemId ? `${base(schoolId)}/${enc(campaignId)}/items/${enc(itemId)}/image` : `${base(schoolId)}/${enc(campaignId)}/image`;

/** PUT multipart: a capa (ou a imagem de um produto). A API tira os metadados da foto antes de guardar. */
export function setCampaignImage(schoolId: string, campaignId: string, file: File, itemId?: string, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  const form = new FormData();
  form.append("file", file, file.name);
  return apiUpload(imagePath(schoolId, campaignId, itemId), form, detailOk, { ...options, method: "PUT" });
}

export function clearCampaignImage(schoolId: string, campaignId: string, itemId?: string, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  return apiSend("DELETE", imagePath(schoolId, campaignId, itemId), undefined, detailOk, options);
}

/** GET da imagem pela API, com a sessao (a gestao ve ate o rascunho). */
export function downloadCampaignImage(schoolId: string, campaignId: string, itemId?: string, options?: RequestOptions): Promise<ApiResult<BlobPayload>> {
  return apiBlob(imagePath(schoolId, campaignId, itemId), options);
}

// ---------------------------------------------------------------- o painel da campanha, os pedidos e a entrega

const PAYMENTS: readonly OrderPaymentStatus[] = ["PENDING", "PAID", "CANCELLED"];
const DELIVERIES: readonly OrderDeliveryStatus[] = ["PENDING", "DELIVERED"];

function parseSoldItem(v: unknown): SoldItem | null {
  if (!isRecord(v)) return null;
  const itemId = str(v.item_id);
  const name = str(v.name);
  const unitsSold = int(v.units_sold);
  const revenueCents = int(v.revenue_cents);
  const costCents = optInt(v.cost_cents);
  if (!itemId || !name || unitsSold === null || revenueCents === null || costCents === undefined || typeof v.cost_known !== "boolean") return null;
  return { itemId, name, unitsSold, revenueCents, costCents, costKnown: v.cost_known };
}

export function parseDashboard(v: unknown): CampaignDashboard | null {
  if (!isRecord(v) || !Array.isArray(v.items)) return null;
  const campaignId = str(v.campaign_id);
  const title = str(v.title);
  const status = typeof v.status === "string" && (CAMPAIGN_STATUSES as readonly string[]).includes(v.status) ? (v.status as CampaignStatus) : null;
  const counts = [v.paid_orders_count, v.pending_orders_count, v.cancelled_orders_count, v.delivered_orders_count, v.to_deliver_orders_count].map(int);
  const collectedCents = int(v.collected_cents);
  const unitsSold = int(v.units_sold);
  const costCents = int(v.cost_cents);
  const profitCents = optInt(v.profit_cents);
  if (!campaignId || !title || !status || counts.some((n) => n === null) || collectedCents === null || unitsSold === null || costCents === null) return null;
  if (typeof v.cost_complete !== "boolean" || profitCents === undefined) return null;
  const items: SoldItem[] = [];
  for (const raw of v.items) {
    const item = parseSoldItem(raw);
    if (!item) return null;
    items.push(item);
  }
  const [paid, pending, cancelled, delivered, toDeliver] = counts as number[];
  return {
    campaignId, title, status,
    paidOrdersCount: paid!, pendingOrdersCount: pending!, cancelledOrdersCount: cancelled!, collectedCents, unitsSold, costCents,
    costComplete: v.cost_complete, profitCents, deliveredOrdersCount: delivered!, toDeliverOrdersCount: toDeliver!, items,
  };
}

function parseOrder(v: unknown): CampaignOrder | null {
  if (!isRecord(v) || !Array.isArray(v.lines)) return null;
  const orderId = str(v.order_id);
  const referenceCode = int(v.reference_code);
  const createdAt = str(v.created_at);
  const amountCents = int(v.amount_cents);
  const guardianName = optStr(v.guardian_name);
  const studentName = optStr(v.student_name);
  const className = optStr(v.class_name);
  const paymentStatus = PAYMENTS.find((p) => p === v.payment_status);
  const deliveryStatus = v.delivery_status === null || v.delivery_status === undefined ? null : DELIVERIES.find((d) => d === v.delivery_status);
  const deliveryChangedAt = optStr(v.delivery_changed_at);
  if (!orderId || referenceCode === null || !createdAt || amountCents === null || !paymentStatus || deliveryStatus === undefined) return null;
  if (guardianName === undefined || studentName === undefined || className === undefined || deliveryChangedAt === undefined) return null;
  const lines = [];
  for (const raw of v.lines) {
    if (!isRecord(raw)) return null;
    const itemName = str(raw.item_name);
    const quantity = int(raw.quantity);
    const unitPriceCents = int(raw.unit_price_cents);
    if (!itemName || quantity === null || unitPriceCents === null) return null;
    lines.push({ itemName, quantity, unitPriceCents });
  }
  return { orderId, referenceCode, createdAt, guardianName, studentName, className, amountCents, paymentStatus, deliveryStatus, deliveryChangedAt, lines };
}

function parseOrderPage(v: unknown): CampaignOrderPage | null {
  if (!isRecord(v) || !Array.isArray(v.items)) return null;
  const total = int(v.total);
  const limit = int(v.limit);
  const offset = int(v.offset);
  if (total === null || limit === null || offset === null) return null;
  const items: CampaignOrder[] = [];
  for (const raw of v.items) {
    const order = parseOrder(raw);
    if (!order) return null;
    items.push(order);
  }
  return { items, total, limit, offset };
}

function parseBuyer(v: unknown): CampaignBuyer | null {
  if (!isRecord(v) || !Array.isArray(v.lines)) return null;
  const guardianName = optStr(v.guardian_name);
  const studentName = optStr(v.student_name);
  const className = optStr(v.class_name);
  const orders = int(v.orders);
  const units = int(v.units);
  const amountCents = int(v.amount_cents);
  if (guardianName === undefined || studentName === undefined || className === undefined || orders === null || units === null || amountCents === null) return null;
  const lines = [];
  for (const raw of v.lines) {
    if (!isRecord(raw)) return null;
    const itemName = str(raw.item_name);
    const quantity = int(raw.quantity);
    if (!itemName || quantity === null) return null;
    lines.push({ itemName, quantity });
  }
  return { guardianName, studentName, className, orders, units, amountCents, lines };
}

export function parseBuyers(v: unknown): CampaignBuyerList | null {
  if (!isRecord(v) || !Array.isArray(v.items) || typeof v.complete !== "boolean") return null;
  const items: CampaignBuyer[] = [];
  for (const raw of v.items) {
    const buyer = parseBuyer(raw);
    if (!buyer) return null;
    items.push(buyer);
  }
  return { items, complete: v.complete };
}

/** GET .../campaigns/{id}/buyers: quem comprou, por responsavel e aluno, com a quantidade de cada produto. */
export function listCampaignBuyers(schoolId: string, campaignId: string, options?: RequestOptions): Promise<ApiResult<CampaignBuyerList>> {
  return apiGet(`${base(schoolId)}/${enc(campaignId)}/buyers`, (body, status) => (status === 200 ? parseBuyers(body) : null), options);
}

/** GET .../campaigns/{id}/dashboard: arrecadado, custos, lucro (so com todos os custos), vendidos e entregas. */
export function getCampaignDashboard(schoolId: string, campaignId: string, options?: RequestOptions): Promise<ApiResult<CampaignDashboard>> {
  return apiGet(`${base(schoolId)}/${enc(campaignId)}/dashboard`, (body, status) => (status === 200 ? parseDashboard(body) : null), options);
}

/** GET .../campaigns/{id}/orders: os pedidos, com filtro de pagamento, de entrega e busca (aluno, turma, responsavel, numero). */
export function listCampaignOrders(schoolId: string, campaignId: string, filters: OrderFilters = {}, options?: RequestOptions): Promise<ApiResult<CampaignOrderPage>> {
  const query = new URLSearchParams();
  if (filters.payment) query.set("payment", filters.payment);
  if (filters.delivery) query.set("delivery", filters.delivery);
  if (filters.search?.trim()) query.set("search", filters.search.trim());
  if (filters.limit !== undefined) query.set("limit", String(filters.limit));
  if (filters.offset !== undefined) query.set("offset", String(filters.offset));
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return apiGet(`${base(schoolId)}/${enc(campaignId)}/orders${suffix}`, (body, status) => (status === 200 ? parseOrderPage(body) : null), options);
}

/** POST .../orders/delivery: marca (ou desmarca) a entrega de ate 100 pedidos aprovados. */
export function changeCampaignDelivery(schoolId: string, campaignId: string, orderIds: string[], delivered: boolean, options?: SendOptions): Promise<ApiResult<DeliveryResult>> {
  return apiSend(
    "POST",
    `${base(schoolId)}/${enc(campaignId)}/orders/delivery`,
    { order_ids: orderIds, delivered },
    (body, status) => {
      if (status !== 200 || !isRecord(body)) return null;
      const changed = int(body.changed);
      const unchanged = int(body.unchanged);
      const skipped = int(body.skipped);
      return changed === null || unchanged === null || skipped === null ? null : { changed, unchanged, skipped };
    },
    options,
  );
}

/** GET .../campaigns/{id}/report.pdf pela API, com a sessao. */
export function downloadCampaignReport(schoolId: string, campaignId: string, options?: RequestOptions): Promise<ApiResult<BlobPayload>> {
  return apiBlob(`${base(schoolId)}/${enc(campaignId)}/report.pdf`, options);
}
