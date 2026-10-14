import { apiBlob, apiGet, apiSend, type BlobPayload, type RequestOptions, type SendOptions } from "./client";
import type { ApiResult, PublicLink, SchoolSettings, SchoolSettingsInput } from "./types";

/**
 * As configuracoes da escola e o link publico (docs/campaigns.md, migracao 0015). A escola do caminho e o
 * `school.id` do vinculo ativo; a API ainda confere contra a sessao. O site so mostra e envia: os limites e a
 * conta dos valores sao da API.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const int = (v: unknown): number | null => (typeof v === "number" && Number.isSafeInteger(v) ? v : null);
const optInt = (v: unknown): number | null | undefined => (v === null || v === undefined ? null : (int(v) ?? undefined));

export function parseSettings(body: unknown): SchoolSettings | null {
  if (!isRecord(body) || !Array.isArray(body.suggested_amounts_cents)) return null;
  const amounts = body.suggested_amounts_cents.map(int);
  const min = int(body.min_contribution_cents);
  const max = int(body.max_contribution_cents);
  const goal = optInt(body.monthly_goal_cents);
  const expected = optInt(body.expected_contributions);
  const text = body.free_amount_text === null || body.free_amount_text === undefined ? null : typeof body.free_amount_text === "string" ? body.free_amount_text : undefined;
  if (amounts.some((a) => a === null) || min === null || max === null || goal === undefined || expected === undefined || text === undefined) return null;
  if (typeof body.allow_custom_amount !== "boolean") return null;
  return {
    suggestedAmountsCents: amounts as number[],
    allowCustomAmount: body.allow_custom_amount,
    minContributionCents: min,
    maxContributionCents: max,
    freeAmountText: text,
    monthlyGoalCents: goal,
    expectedContributions: expected,
  };
}

function parseLink(body: unknown): PublicLink | null {
  if (!isRecord(body)) return null;
  const { school_name: schoolName, slug, url } = body;
  if (typeof schoolName !== "string" || typeof slug !== "string" || typeof url !== "string" || !/^https?:\/\//.test(url)) return null;
  return { schoolName, slug, url };
}

const base = (schoolId: string) => `/api/v1/schools/${encodeURIComponent(schoolId)}`;
const settingsOk = (body: unknown, status: number) => (status === 200 ? parseSettings(body) : null);

/** GET .../settings: valores sugeridos, texto, metas. */
export function getSchoolSettings(schoolId: string, options?: RequestOptions): Promise<ApiResult<SchoolSettings>> {
  return apiGet(`${base(schoolId)}/settings`, settingsOk, options);
}

/** PATCH .../settings: so o que foi enviado muda; `null` apaga o texto e as metas. */
export function updateSchoolSettings(schoolId: string, changes: SchoolSettingsInput, options?: SendOptions): Promise<ApiResult<SchoolSettings>> {
  const body: Record<string, unknown> = {};
  if (changes.suggestedAmountsCents !== undefined) body.suggested_amounts_cents = changes.suggestedAmountsCents;
  if (changes.allowCustomAmount !== undefined) body.allow_custom_amount = changes.allowCustomAmount;
  if (changes.freeAmountText !== undefined) body.free_amount_text = changes.freeAmountText;
  if (changes.monthlyGoalCents !== undefined) body.monthly_goal_cents = changes.monthlyGoalCents;
  if (changes.expectedContributions !== undefined) body.expected_contributions = changes.expectedContributions;
  return apiSend("PATCH", `${base(schoolId)}/settings`, body, settingsOk, options);
}

/** GET .../public-link: o endereco que as familias abrem (e que o QR Code leva). */
export function getPublicLink(schoolId: string, options?: RequestOptions): Promise<ApiResult<PublicLink>> {
  return apiGet(`${base(schoolId)}/public-link`, (body, status) => (status === 200 ? parseLink(body) : null), options);
}

/** GET .../public-link/poster.pdf: o cartaz A4 com o QR Code, pela API, com a sessao. */
export function downloadPoster(schoolId: string, options?: RequestOptions): Promise<ApiResult<BlobPayload>> {
  return apiBlob(`${base(schoolId)}/public-link/poster.pdf`, options);
}
