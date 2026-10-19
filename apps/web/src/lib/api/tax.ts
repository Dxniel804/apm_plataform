import { apiGet, apiSend, type RequestOptions, type SendOptions } from "./client";
import type { ApiResult } from "./types";

/**
 * Impostos retidos (docs/tax-guides.md). O site NAO decide a lei nem fala com a Receita: a escola escreve as
 * regras (lendo a lei e os sites do governo), a API calcula e soma, e o site mostra o que digitar no site da Receita. Dinheiro em
 * centavos; a aliquota em pontos-base (1,5% = 150).
 */

export type TaxKind = "IRRF" | "INSS" | "ISS" | "OTHER";
export type TaxApplies = "PF" | "PJ" | "BOTH";
export type DueRoll = "PREVIOUS" | "NEXT";
const KINDS: readonly TaxKind[] = ["IRRF", "INSS", "ISS", "OTHER"];
const APPLIES: readonly TaxApplies[] = ["PF", "PJ", "BOTH"];
const ROLLS: readonly DueRoll[] = ["PREVIOUS", "NEXT"];

export interface TaxRule {
  id: string;
  ruleKey: string;
  label: string;
  taxKind: TaxKind;
  appliesTo: TaxApplies;
  rateBps: number;
  baseCapCents: number | null;
  minTotalCents: number;
  darfCode: string | null;
  howto: string | null;
  dueDay: number;
  dueRoll: DueRoll;
  sourceNote: string | null;
  validated: boolean;
  validatedAt: string | null;
}

export interface TaxSuggestion {
  ruleKey: string;
  label: string;
  taxKind: TaxKind;
  appliesTo: TaxApplies;
  rateBps: number | null;
  baseCapCents: number | null;
  darfCode: string | null;
  howto: string | null;
  warning: string;
}

export interface TaxRetention {
  id: string;
  ruleKey: string;
  ruleLabel: string;
  providerKind: "PF" | "PJ";
  providerName: string;
  competence: string;
  grossCents: number;
  baseCents: number;
  retainedCents: number;
  netCents: number;
  rateBps: number;
  note: string | null;
  voided: boolean;
  validated: boolean;
}

export interface TaxGuide {
  ruleKey: string;
  label: string;
  taxKind: TaxKind;
  darfCode: string | null;
  howto: string | null;
  competence: string;
  dueDate: string;
  totalCents: number;
  count: number;
  minTotalCents: number;
  belowMinimum: boolean;
  validated: boolean;
  mixedVersions: boolean;
  siteUrl: string | null;
}

export interface TaxMonth {
  period: string;
  retentions: TaxRetention[];
  guides: TaxGuide[];
}

export interface TaxRules {
  rules: TaxRule[];
  suggestions: TaxSuggestion[];
}

const enc = encodeURIComponent;
const school = (schoolId: string) => `/api/v1/schools/${enc(schoolId)}/tax`;
const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const int = (v: unknown): number | null => (typeof v === "number" && Number.isSafeInteger(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const nint = (v: unknown): number | null | undefined => (v === null || v === undefined ? null : (int(v) ?? undefined));
const oneOf = <T extends string>(list: readonly T[], v: unknown): T | null => (typeof v === "string" && (list as readonly string[]).includes(v) ? (v as T) : null);

function list<T>(value: unknown, parse: (raw: unknown) => T | null): T[] | null {
  if (!Array.isArray(value) || value.length > 2000) return null;
  const out: T[] = [];
  for (const raw of value) {
    const parsed = parse(raw);
    if (parsed === null) return null;
    out.push(parsed);
  }
  return out;
}

function parseRule(raw: unknown): TaxRule | null {
  if (!isRecord(raw)) return null;
  const id = str(raw.id);
  const ruleKey = str(raw.rule_key);
  const label = str(raw.label);
  const taxKind = oneOf(KINDS, raw.tax_kind);
  const appliesTo = oneOf(APPLIES, raw.applies_to);
  const rateBps = int(raw.rate_bps);
  const baseCapCents = nint(raw.base_cap_cents);
  const minTotalCents = int(raw.min_total_cents);
  const dueDay = int(raw.due_day);
  const dueRoll = oneOf(ROLLS, raw.due_roll);
  if (!id || !ruleKey || !label || !taxKind || !appliesTo || rateBps === null || baseCapCents === undefined || minTotalCents === null || dueDay === null || !dueRoll) return null;
  if (typeof raw.validated !== "boolean") return null;
  return { id, ruleKey, label, taxKind, appliesTo, rateBps, baseCapCents, minTotalCents, darfCode: str(raw.darf_code), howto: str(raw.howto), dueDay, dueRoll, sourceNote: str(raw.source_note), validated: raw.validated, validatedAt: str(raw.validated_at) };
}

function parseSuggestion(raw: unknown): TaxSuggestion | null {
  if (!isRecord(raw)) return null;
  const ruleKey = str(raw.rule_key);
  const label = str(raw.label);
  const taxKind = oneOf(KINDS, raw.tax_kind);
  const appliesTo = oneOf(APPLIES, raw.applies_to);
  const rateBps = nint(raw.rate_bps);
  const baseCapCents = nint(raw.base_cap_cents);
  const warning = str(raw.warning);
  if (!ruleKey || !label || !taxKind || !appliesTo || rateBps === undefined || baseCapCents === undefined || !warning) return null;
  return { ruleKey, label, taxKind, appliesTo, rateBps, baseCapCents, darfCode: str(raw.darf_code), howto: str(raw.howto), warning };
}

export function parseRules(body: unknown): TaxRules | null {
  if (!isRecord(body)) return null;
  const rules = list(body.rules, parseRule);
  const suggestions = list(body.suggestions, parseSuggestion);
  return rules && suggestions ? { rules, suggestions } : null;
}

function parseRetention(raw: unknown): TaxRetention | null {
  if (!isRecord(raw)) return null;
  const id = str(raw.id);
  const ruleKey = str(raw.rule_key);
  const ruleLabel = str(raw.rule_label);
  const providerKind = oneOf(["PF", "PJ"] as const, raw.provider_kind);
  const providerName = str(raw.provider_name);
  const competence = str(raw.competence);
  const grossCents = int(raw.gross_cents);
  const baseCents = int(raw.base_cents);
  const retainedCents = int(raw.retained_cents);
  const netCents = int(raw.net_cents);
  const rateBps = int(raw.rate_bps);
  if (!id || !ruleKey || !ruleLabel || !providerKind || !providerName || !competence || grossCents === null || baseCents === null || retainedCents === null || netCents === null || rateBps === null) return null;
  if (typeof raw.voided !== "boolean" || typeof raw.validated !== "boolean") return null;
  return { id, ruleKey, ruleLabel, providerKind, providerName, competence, grossCents, baseCents, retainedCents, netCents, rateBps, note: str(raw.note), voided: raw.voided, validated: raw.validated };
}

function parseGuide(raw: unknown): TaxGuide | null {
  if (!isRecord(raw)) return null;
  const ruleKey = str(raw.rule_key);
  const label = str(raw.label);
  const taxKind = oneOf(KINDS, raw.tax_kind);
  const competence = str(raw.competence);
  const dueDate = str(raw.due_date);
  const totalCents = int(raw.total_cents);
  const count = int(raw.count);
  const minTotalCents = int(raw.min_total_cents);
  if (!ruleKey || !label || !taxKind || !competence || !dueDate || totalCents === null || count === null || minTotalCents === null) return null;
  if (typeof raw.below_minimum !== "boolean" || typeof raw.validated !== "boolean" || typeof raw.mixed_versions !== "boolean") return null;
  return { ruleKey, label, taxKind, darfCode: str(raw.darf_code), howto: str(raw.howto), competence, dueDate, totalCents, count, minTotalCents, belowMinimum: raw.below_minimum, validated: raw.validated, mixedVersions: raw.mixed_versions, siteUrl: str(raw.site_url) };
}

export function parseTaxMonth(body: unknown): TaxMonth | null {
  if (!isRecord(body) || typeof body.period !== "string") return null;
  const retentions = list(body.retentions, parseRetention);
  const guides = list(body.guides, parseGuide);
  return retentions && guides ? { period: body.period, retentions, guides } : null;
}

export function getTaxRules(schoolId: string, options?: RequestOptions): Promise<ApiResult<TaxRules>> {
  return apiGet(`${school(schoolId)}/rules`, (body, status) => (status === 200 ? parseRules(body) : null), options);
}

export function getTaxMonth(schoolId: string, period: string, options?: RequestOptions): Promise<ApiResult<TaxMonth>> {
  return apiGet(`${school(schoolId)}/month?period=${enc(period)}`, (body, status) => (status === 200 ? parseTaxMonth(body) : null), options);
}

export interface RuleInput {
  ruleKey: string;
  label: string;
  taxKind: TaxKind;
  appliesTo: TaxApplies;
  rateBps: number;
  baseCapCents?: number;
  minTotalCents: number;
  darfCode?: string;
  howto?: string;
  dueDay: number;
  dueRoll: DueRoll;
  sourceNote?: string;
  validated: boolean;
}

const saved = (body: unknown, status: number) => (status === 201 && isRecord(body) ? { ok: true as const } : null);

export function saveTaxRule(schoolId: string, input: RuleInput, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  const body: Record<string, string | number | boolean> = {
    rule_key: input.ruleKey,
    label: input.label,
    tax_kind: input.taxKind,
    applies_to: input.appliesTo,
    rate_bps: input.rateBps,
    min_total_cents: input.minTotalCents,
    due_day: input.dueDay,
    due_roll: input.dueRoll,
    validated: input.validated,
  };
  if (input.baseCapCents) body.base_cap_cents = input.baseCapCents;
  if (input.darfCode) body.darf_code = input.darfCode;
  if (input.howto) body.howto = input.howto;
  if (input.sourceNote) body.source_note = input.sourceNote;
  return apiSend("POST", `${school(schoolId)}/rules`, body, saved, options);
}

export interface TaxPreview {
  baseCents: number;
  retainedCents: number;
  netCents: number;
  rateBps: number;
}

export function previewTax(schoolId: string, ruleId: string, providerKind: "PF" | "PJ", grossCents: number, options?: RequestOptions): Promise<ApiResult<TaxPreview>> {
  return apiGet(
    `${school(schoolId)}/preview?rule_id=${enc(ruleId)}&provider_kind=${providerKind}&gross_cents=${grossCents}`,
    (body, status) => {
      if (status !== 200 || !isRecord(body)) return null;
      const baseCents = int(body.base_cents);
      const retainedCents = int(body.retained_cents);
      const netCents = int(body.net_cents);
      const rateBps = int(body.rate_bps);
      return baseCents === null || retainedCents === null || netCents === null || rateBps === null ? null : { baseCents, retainedCents, netCents, rateBps };
    },
    options,
  );
}

export interface RetentionInput {
  ruleId: string;
  providerKind: "PF" | "PJ";
  providerName: string;
  competence: string;
  grossCents: number;
  note?: string;
}

export function addTaxRetention(schoolId: string, input: RetentionInput, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  const body: Record<string, string | number> = { rule_id: input.ruleId, provider_kind: input.providerKind, provider_name: input.providerName, competence: input.competence, gross_cents: input.grossCents };
  if (input.note) body.note = input.note;
  return apiSend("POST", `${school(schoolId)}/retentions`, body, saved, options);
}

export function voidTaxRetention(schoolId: string, id: string, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  return apiSend("POST", `${school(schoolId)}/retentions/${enc(id)}/void`, {}, (body, status) => (status === 200 && isRecord(body) ? { ok: true as const } : null), options);
}
