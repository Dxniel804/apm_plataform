import { apiGet, apiSend, type RequestOptions, type SendOptions } from "./client";
import {
  API_FIELD,
  IDENTIFICATION_FIELDS,
  type FieldRule,
  type IdentificationConfig,
} from "../validation";
import { parseContributionStatus, parsePixStatus } from "../status";
import type {
  ApiResult,
  ContributionState,
  CreateContributionInput,
  CreateOrderInput,
  CreatedContribution,
  PixCharge,
  PublicCampaign,
  PublicCampaignItem,
  PublicCampaignSummary,
  PublicSchool,
  Receipt,
  ReceiptItem,
} from "./types";

/**
 * Portal publico REAL (docs/public-flow.md). Sem login. Regras:
 * - a escola vem do slug da URL; nenhum id interno circula;
 * - a Idempotency-Key e tao secreta quanto o token: so vai no cabecalho do POST, nunca em URL,
 *   log ou armazenamento (quem gera e guarda so em memoria e o fluxo da pagina);
 * - o cliente NUNCA afirma pagamento: so repassa o status que a API devolveu.
 */

const BASE = "/api/v1/public/schools";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function cents(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

const RULES: readonly FieldRule[] = ["REQUIRED", "OPTIONAL", "HIDDEN"];

/** Campo que a API nao mencionou (ou com valor estranho) fica OCULTO: na duvida, nao pede o dado. */
function parseIdentification(value: unknown): IdentificationConfig {
  const source = isRecord(value) ? value : {};
  const config = {} as IdentificationConfig;
  for (const field of IDENTIFICATION_FIELDS) {
    const raw = source[API_FIELD[field]];
    config[field] = typeof raw === "string" && (RULES as readonly string[]).includes(raw) ? (raw as FieldRule) : "HIDDEN";
  }
  return config;
}

export function parsePublicSchool(body: unknown): PublicSchool | null {
  if (!isRecord(body)) return null;
  const slug = str(body.slug);
  const name = str(body.name);
  const apmName = str(body.apm_name);
  const accentColor = str(body.accent_color);
  const min = cents(body.min_amount_cents);
  const max = cents(body.max_amount_cents);
  if (!slug || !name || !apmName || !accentColor || min === null || max === null) return null;
  if (!/^#[0-9a-fA-F]{6}$/.test(accentColor)) return null;
  if (!Array.isArray(body.suggested_amounts_cents) || typeof body.allow_custom_amount !== "boolean") return null;
  const suggested: number[] = [];
  for (const item of body.suggested_amounts_cents) {
    const value = cents(item);
    if (value === null || value === 0) return null;
    suggested.push(value);
  }
  return {
    slug,
    name,
    apmName,
    accentColor,
    suggestedAmountsCents: suggested,
    allowCustomAmount: body.allow_custom_amount,
    minAmountCents: min,
    maxAmountCents: max,
    identification: parseIdentification(body.identification),
  };
}

function parseCharge(value: unknown): PixCharge | null {
  if (!isRecord(value)) return null;
  const status = parsePixStatus(value.status);
  const amountCents = cents(value.amount_cents);
  const expiresAt = str(value.expires_at);
  const payload = value.emv_payload === null || value.emv_payload === undefined ? null : str(value.emv_payload);
  if (!status || amountCents === null || !expiresAt) return null;
  if (value.emv_payload !== null && value.emv_payload !== undefined && payload === null) return null;
  return { status, amountCents, emvPayload: payload, expiresAt };
}

export function parseContributionState(body: unknown): ContributionState | null {
  if (!isRecord(body)) return null;
  const status = parseContributionStatus(body.status);
  const amountCents = cents(body.amount_cents);
  if (!status || amountCents === null) return null;
  let charge: PixCharge | null = null;
  if (body.charge !== null && body.charge !== undefined) {
    charge = parseCharge(body.charge);
    if (!charge) return null;
  }
  return { status, amountCents, charge };
}

function parseCreated(body: unknown, status: number): CreatedContribution | null {
  if (status !== 201 && status !== 200) return null;
  const state = parseContributionState(body);
  const token = isRecord(body) ? str(body.token) : null;
  return state && token && /^[A-Za-z0-9_-]{22,64}$/.test(token) ? { ...state, token } : null;
}

function parseReceipt(body: unknown, status: number): Receipt | null {
  if (status !== 200 || !isRecord(body) || body.status !== "PAID") return null;
  const referenceCode = str(body.reference_code);
  const amountCents = cents(body.amount_cents);
  const paidAt = str(body.paid_at);
  const schoolName = str(body.school_name);
  const method = str(body.method);
  if (!referenceCode || amountCents === null || !paidAt || !schoolName || !method) return null;
  // Um comprovante de uma contribuicao comum nao tem campanha nem itens (a API manda null e []).
  const campaignTitle = body.campaign_title === null || body.campaign_title === undefined ? null : str(body.campaign_title);
  if (body.campaign_title !== null && body.campaign_title !== undefined && campaignTitle === null) return null;
  const items: ReceiptItem[] = [];
  if (body.items !== undefined) {
    if (!Array.isArray(body.items)) return null;
    for (const raw of body.items) {
      if (!isRecord(raw)) return null;
      const name = str(raw.name);
      const unitPriceCents = cents(raw.unit_price_cents);
      const quantity = typeof raw.quantity === "number" && Number.isSafeInteger(raw.quantity) && raw.quantity > 0 ? raw.quantity : null;
      if (!name || unitPriceCents === null || quantity === null) return null;
      items.push({ name, unitPriceCents, quantity });
    }
  }
  return { status: "PAID", referenceCode, amountCents, paidAt, schoolName, method, campaignTitle, items };
}

// --- as campanhas a venda (docs/campaigns.md) ---------------------------------------------------------

function parseCampaignItem(value: unknown): PublicCampaignItem | null {
  if (!isRecord(value)) return null;
  const id = str(value.id);
  const name = str(value.name);
  const priceCents = cents(value.price_cents);
  const imageVersion = cents(value.image_version);
  const description = value.description === null || value.description === undefined ? null : str(value.description);
  const maxPerOrder = value.max_per_order === null || value.max_per_order === undefined ? null : cents(value.max_per_order);
  if (!id || !name || priceCents === null || priceCents === 0 || imageVersion === null || typeof value.has_image !== "boolean") return null;
  if ((value.description !== null && value.description !== undefined && description === null) || (value.max_per_order != null && maxPerOrder === null)) return null;
  return { id, name, description, priceCents, maxPerOrder, hasImage: value.has_image, imageVersion };
}

function parseCampaignSummary(value: unknown): PublicCampaignSummary | null {
  if (!isRecord(value)) return null;
  const id = str(value.id);
  const title = str(value.title);
  const itemsCount = cents(value.items_count);
  const coverVersion = cents(value.cover_version);
  const description = value.description === null || value.description === undefined ? null : str(value.description);
  const endsOn = value.ends_on === null || value.ends_on === undefined ? null : str(value.ends_on);
  if (!id || !title || itemsCount === null || coverVersion === null || typeof value.has_cover !== "boolean") return null;
  if ((value.description != null && description === null) || (value.ends_on != null && endsOn === null)) return null;
  // Campanhas antigas, de antes do campo existir, nao pedem aluno e turma.
  const askStudentClass = typeof value.ask_student_class === "boolean" ? value.ask_student_class : false;
  return { id, title, description, endsOn, hasCover: value.has_cover, coverVersion, itemsCount, askStudentClass };
}

export function parsePublicCampaign(body: unknown): PublicCampaign | null {
  const summary = parseCampaignSummary(body);
  if (!summary || !isRecord(body) || !Array.isArray(body.items)) return null;
  const items: PublicCampaignItem[] = [];
  for (const raw of body.items) {
    const item = parseCampaignItem(raw);
    if (!item) return null;
    items.push(item);
  }
  return { ...summary, items };
}

function parseCampaignList(body: unknown, status: number): PublicCampaignSummary[] | null {
  if (status !== 200 || !isRecord(body) || !Array.isArray(body.campaigns)) return null;
  const campaigns: PublicCampaignSummary[] = [];
  for (const raw of body.campaigns) {
    const campaign = parseCampaignSummary(raw);
    if (!campaign) return null;
    campaigns.push(campaign);
  }
  return campaigns;
}

const enc = encodeURIComponent;

/** Enderecos das imagens publicas de uma campanha a venda: o `v` so serve para trocar a imagem em cache. */
export const campaignCoverUrl = (slug: string, campaignId: string, version: number) =>
  `${BASE}/${encodeURIComponent(slug)}/campaigns/${encodeURIComponent(campaignId)}/cover?v=${version}`;
export const campaignItemImageUrl = (slug: string, campaignId: string, itemId: string, version: number) =>
  `${BASE}/${encodeURIComponent(slug)}/campaigns/${encodeURIComponent(campaignId)}/items/${encodeURIComponent(itemId)}/image?v=${version}`;

/** GET /public/schools/{slug}. */
export function getPublicSchool(slug: string, options?: RequestOptions): Promise<ApiResult<PublicSchool>> {
  return apiGet(`${BASE}/${enc(slug)}`, (body, status) => (status === 200 ? parsePublicSchool(body) : null), options);
}

/** Corpo do POST: so os campos preenchidos, com os nomes da API (a API ainda descarta o que a escola oculta). */
export function contributionBody(input: CreateContributionInput): Record<string, string | number> {
  const body: Record<string, string | number> = { amount_cents: input.amountCents };
  for (const field of IDENTIFICATION_FIELDS) {
    const value = input.identification[field];
    if (value) body[API_FIELD[field]] = value;
  }
  return body;
}

/**
 * POST /public/schools/{slug}/contributions. `idempotencyKey` (uuid) e gerada UMA vez por tentativa
 * pelo chamador: repetir o POST com a mesma chave devolve a mesma contribuicao (nao duplica).
 */
export function createContribution(
  slug: string,
  input: CreateContributionInput,
  idempotencyKey: string,
  options: SendOptions = {},
): Promise<ApiResult<CreatedContribution>> {
  return apiSend("POST", `${BASE}/${enc(slug)}/contributions`, contributionBody(input), parseCreated, {
    ...options,
    headers: { ...options.headers, "Idempotency-Key": idempotencyKey },
  });
}

/** GET .../campaigns: as campanhas a venda na escola (pode ser uma lista vazia). */
export function getPublicCampaigns(slug: string, options?: RequestOptions): Promise<ApiResult<PublicCampaignSummary[]>> {
  return apiGet(`${BASE}/${enc(slug)}/campaigns`, parseCampaignList, options);
}

/** GET .../campaigns/{id}: uma campanha a venda, com os produtos e os precos de hoje. 404 unico para qualquer outra. */
export function getPublicCampaign(slug: string, campaignId: string, options?: RequestOptions): Promise<ApiResult<PublicCampaign>> {
  return apiGet(`${BASE}/${enc(slug)}/campaigns/${enc(campaignId)}`, (body, status) => (status === 200 ? parsePublicCampaign(body) : null), options);
}

/** Corpo do pedido: QUAIS produtos e QUANTOS, mais a identificacao. Nunca um preco nem um total. */
export function orderBody(input: CreateOrderInput): Record<string, unknown> {
  const body: Record<string, unknown> = { lines: input.lines.map((line) => ({ item_id: line.itemId, quantity: line.quantity })) };
  for (const field of IDENTIFICATION_FIELDS) {
    const value = input.identification[field];
    if (value) body[API_FIELD[field]] = value;
  }
  return body;
}

/**
 * POST .../campaigns/{id}/orders: cria o pedido e o Pix. A `Idempotency-Key` e uma por tentativa (como na
 * contribuicao): repetir o POST com o mesmo carrinho devolve o mesmo pedido.
 */
export function createOrder(
  slug: string,
  campaignId: string,
  input: CreateOrderInput,
  idempotencyKey: string,
  options: SendOptions = {},
): Promise<ApiResult<CreatedContribution>> {
  return apiSend("POST", `${BASE}/${enc(slug)}/campaigns/${enc(campaignId)}/orders`, orderBody(input), parseCreated, {
    ...options,
    headers: { ...options.headers, "Idempotency-Key": idempotencyKey },
  });
}

const parseStateOk = (body: unknown, status: number) => (status === 200 ? parseContributionState(body) : null);

/** GET .../contributions/{token}/charge: o polling da tela do Pix. */
export function getContribution(slug: string, token: string, options?: RequestOptions): Promise<ApiResult<ContributionState>> {
  return apiGet(`${BASE}/${enc(slug)}/contributions/${enc(token)}/charge`, parseStateOk, options);
}

/** POST .../contributions/{token}/charges: novo Pix quando o anterior expirou (a API nao duplica). */
export function renewCharge(slug: string, token: string, options?: SendOptions): Promise<ApiResult<ContributionState>> {
  return apiSend("POST", `${BASE}/${enc(slug)}/contributions/${enc(token)}/charges`, undefined, parseStateOk, options);
}

/** GET .../contributions/{token}/receipt: 200 so pago; 409 enquanto nao; 404 unico para qualquer token ruim. */
export function getReceipt(slug: string, token: string, options?: RequestOptions): Promise<ApiResult<Receipt>> {
  return apiGet(`${BASE}/${enc(slug)}/contributions/${enc(token)}/receipt`, parseReceipt, options);
}

const SANDBOX_PREFIX = "PIX-SANDBOX:";

/** O sandbox de desenvolvimento publica `PIX-SANDBOX:<txid>:<valor>`; so nesse caso existe o botao de simular. */
export function sandboxTxid(payload: string | null): string | null {
  if (!payload?.startsWith(SANDBOX_PREFIX)) return null;
  const txid = payload.slice(SANDBOX_PREFIX.length).split(":")[0] ?? "";
  return /^[A-Za-z0-9_-]{8,128}$/.test(txid) ? txid : null;
}

/** POST /dev/sandbox/pix/{txid}/pay: so desenvolvimento (a API responde 404 fora dele). Nao confirma nada no cliente. */
export function sandboxPay(txid: string, options?: SendOptions): Promise<ApiResult<{ status: string }>> {
  return apiSend(
    "POST",
    `/api/v1/dev/sandbox/pix/${enc(txid)}/pay`,
    {},
    (body) => (isRecord(body) && typeof body.status === "string" ? { status: body.status } : null),
    options,
  );
}
