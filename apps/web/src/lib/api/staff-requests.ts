import { apiBlob, apiGet, apiSend, apiUpload, type BlobPayload, type RequestOptions, type SendOptions } from "./client";
import type {
  ApiResult,
  Page,
  RequestCategory,
  RequestPhoto,
  RequestStatus,
  StaffRequestDetail,
  StaffRequestInput,
  StaffRequestSummary,
} from "./types";

/**
 * Solicitacoes REAIS (docs/staff-requests.md). A escola do caminho e o `school.id` do vinculo ativo; a API
 * ainda confere contra a sessao. O site nunca decide estado: mostra o que a API devolve. As fotos so vao no
 * corpo multipart e voltam pela API com o cookie de sessao (nunca ha URL publica).
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const int = (v: unknown): number | null => (typeof v === "number" && Number.isSafeInteger(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const optStr = (v: unknown): string | null | undefined => (v === null || v === undefined ? null : typeof v === "string" ? v : undefined);
const oneOf = <T extends string>(list: readonly T[], v: unknown): T | null => (typeof v === "string" && (list as readonly string[]).includes(v) ? (v as T) : null);

export const REQUEST_CATEGORIES: readonly RequestCategory[] = ["SUPPLIES", "MAINTENANCE", "EVENT", "FINANCE", "OTHER"];
export const REQUEST_STATUSES: readonly RequestStatus[] = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"];

function parseSummary(v: unknown): StaffRequestSummary | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const category = oneOf(REQUEST_CATEGORIES, v.category);
  const title = str(v.title);
  const status = oneOf(REQUEST_STATUSES, v.status);
  const authorUserId = str(v.author_user_id);
  const attachmentsCount = int(v.attachments_count);
  const createdAt = str(v.created_at);
  const updatedAt = str(v.updated_at);
  const resolvedAt = optStr(v.resolved_at);
  if (!id || !category || !title || !status || !authorUserId || attachmentsCount === null || !createdAt || !updatedAt || resolvedAt === undefined) return null;
  return { id, category, title, status, authorUserId, attachmentsCount, createdAt, updatedAt, resolvedAt };
}

function parsePhoto(v: unknown): RequestPhoto | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const fileName = str(v.file_name);
  const contentType = str(v.content_type);
  const sizeBytes = int(v.size_bytes);
  const uploadedByUserId = str(v.uploaded_by_user_id);
  const createdAt = str(v.created_at);
  return id && fileName && contentType && sizeBytes !== null && uploadedByUserId && createdAt
    ? { id, fileName, contentType, sizeBytes, uploadedByUserId, createdAt }
    : null;
}

export function parseStaffRequestDetail(v: unknown): StaffRequestDetail | null {
  const base = parseSummary(v);
  if (!base || !isRecord(v) || !Array.isArray(v.attachments)) return null;
  const photos: RequestPhoto[] = [];
  for (const raw of v.attachments) {
    const photo = parsePhoto(raw);
    if (!photo) return null;
    photos.push(photo);
  }
  const description = optStr(v.description);
  const startedAt = optStr(v.started_at);
  const startedByUserId = optStr(v.started_by_user_id);
  const resolvedByUserId = optStr(v.resolved_by_user_id);
  const resolutionNote = optStr(v.resolution_note);
  if ([description, startedAt, startedByUserId, resolvedByUserId, resolutionNote].some((x) => x === undefined)) return null;
  return {
    ...base,
    description: description as string | null,
    startedAt: startedAt as string | null,
    startedByUserId: startedByUserId as string | null,
    resolvedByUserId: resolvedByUserId as string | null,
    resolutionNote: resolutionNote as string | null,
    photos,
  };
}

function parsePage(body: unknown): Page<StaffRequestSummary> | null {
  if (!isRecord(body) || !Array.isArray(body.items)) return null;
  const items: StaffRequestSummary[] = [];
  for (const raw of body.items) {
    const item = parseSummary(raw);
    if (!item) return null;
    items.push(item);
  }
  const next = body.next_cursor;
  if (next !== null && next !== undefined && (typeof next !== "string" || next.length === 0 || next.length > 500)) return null;
  return { items, nextCursor: typeof next === "string" ? next : null };
}

const enc = encodeURIComponent;
const base = (schoolId: string) => `/api/v1/schools/${enc(schoolId)}`;
const detailOk = (body: unknown, status: number) => (status === 200 ? parseStaffRequestDetail(body) : null);

function query(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${enc(String(v))}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

/** GET .../requests: `read_all` ve a escola toda; os demais, so as proprias. Mais recentes primeiro. */
export function listStaffRequests(
  schoolId: string,
  params: { status?: RequestStatus; category?: RequestCategory; period?: string; cursor?: string; limit?: number } = {},
  options?: RequestOptions,
): Promise<ApiResult<Page<StaffRequestSummary>>> {
  return apiGet(
    `${base(schoolId)}/requests${query({ status: params.status, category: params.category, period: params.period, cursor: params.cursor, limit: params.limit })}`,
    (body, status) => (status === 200 ? parsePage(body) : null),
    options,
  );
}

export function getStaffRequest(schoolId: string, requestId: string, options?: RequestOptions): Promise<ApiResult<StaffRequestDetail>> {
  return apiGet(`${base(schoolId)}/requests/${enc(requestId)}`, detailOk, options);
}

/** POST .../requests: abre um pedido. Quem escreve e o autor (vem da sessao; o nome nunca e pedido). */
export function createStaffRequest(schoolId: string, input: StaffRequestInput, options?: SendOptions): Promise<ApiResult<StaffRequestDetail>> {
  const body: Record<string, string> = { category: input.category, title: input.title };
  if (input.description) body.description = input.description;
  return apiSend("POST", `${base(schoolId)}/requests`, body, (b, s) => (s === 201 || s === 200 ? parseStaffRequestDetail(b) : null), options);
}

/** POST .../attachments (multipart): so o autor, so enquanto o pedido esta aberto (`409 attachments_closed`). */
export function uploadRequestPhoto(schoolId: string, requestId: string, file: File, options?: SendOptions): Promise<ApiResult<RequestPhoto>> {
  const form = new FormData();
  form.append("file", file, file.name);
  return apiUpload(`${base(schoolId)}/requests/${enc(requestId)}/attachments`, form, (body, status) => (status === 201 || status === 200 ? parsePhoto(body) : null), options);
}

/** GET .../attachments/{id}: a foto pela API, com a sessao. Nunca uma URL publica. */
export function downloadRequestPhoto(schoolId: string, requestId: string, photoId: string, options?: RequestOptions): Promise<ApiResult<BlobPayload>> {
  return apiBlob(`${base(schoolId)}/requests/${enc(requestId)}/attachments/${enc(photoId)}`, options);
}

const action = (schoolId: string, requestId: string, name: string, body: unknown, options?: SendOptions) =>
  apiSend("POST", `${base(schoolId)}/requests/${enc(requestId)}/${name}`, body, detailOk, options);

export const startStaffRequest = (schoolId: string, requestId: string, options?: SendOptions) => action(schoolId, requestId, "start", undefined, options);
export const cancelStaffRequest = (schoolId: string, requestId: string, options?: SendOptions) => action(schoolId, requestId, "cancel", undefined, options);

/** Resolve o pedido; a nota (opcional) e o que o autor le. */
export function resolveStaffRequest(schoolId: string, requestId: string, note?: string, options?: SendOptions): Promise<ApiResult<StaffRequestDetail>> {
  return action(schoolId, requestId, "resolve", note ? { note } : undefined, options);
}
