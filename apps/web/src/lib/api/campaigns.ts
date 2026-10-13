import { apiBlob, apiGet, apiSend, apiUpload, type BlobPayload, type RequestOptions, type SendOptions } from "./client";
import type {
  ApiResult,
  CampaignDetail,
  CampaignInput,
  CampaignItem,
  CampaignItemInput,
  CampaignStatus,
  CampaignSummary,
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
  const maxPerOrder = optInt(v.max_per_order);
  const position = int(v.position);
  const imageVersion = int(v.image_version);
  if (!id || !name || description === undefined || priceCents === null || priceCents < 0 || maxPerOrder === undefined) return null;
  if (position === null || imageVersion === null || typeof v.is_active !== "boolean" || typeof v.has_image !== "boolean") return null;
  return { id, name, description, priceCents, maxPerOrder, position, isActive: v.is_active, hasImage: v.has_image, imageVersion };
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
  if (description === undefined || coverVersion === null) return null;
  return { ...base, description, coverVersion, items };
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
  return apiSend("POST", base(schoolId), body, detailOk, options);
}

/** PATCH: so o que foi enviado muda; `null` apaga um campo opcional (texto, datas). */
export function updateCampaign(schoolId: string, campaignId: string, changes: Partial<CampaignInput>, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  const body: Record<string, unknown> = {};
  if (changes.title !== undefined) body.title = changes.title;
  if (changes.description !== undefined) body.description = changes.description;
  if (changes.startsOn !== undefined) body.starts_on = changes.startsOn;
  if (changes.endsOn !== undefined) body.ends_on = changes.endsOn;
  return apiSend("PATCH", `${base(schoolId)}/${enc(campaignId)}`, body, detailOk, options);
}

export const activateCampaign = (schoolId: string, campaignId: string, options?: SendOptions) =>
  apiSend("POST", `${base(schoolId)}/${enc(campaignId)}/activate`, undefined, detailOk, options);
export const endCampaign = (schoolId: string, campaignId: string, options?: SendOptions) =>
  apiSend("POST", `${base(schoolId)}/${enc(campaignId)}/end`, undefined, detailOk, options);

export function addCampaignItem(schoolId: string, campaignId: string, input: CampaignItemInput, options?: SendOptions): Promise<ApiResult<CampaignDetail>> {
  const body: Record<string, unknown> = { name: input.name, price_cents: input.priceCents };
  if (input.description) body.description = input.description;
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
