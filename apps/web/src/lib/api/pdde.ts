import { apiGet, apiSend, type RequestOptions, type SendOptions } from "./client";
import type { ApiResult } from "./types";

/**
 * PDDE: a prestacao de contas do dinheiro federal (docs/m8-pdde-plan.md). A conta bancaria do PDDE tem as suas
 * linhas classificadas (programa, custeio ou capital, objeto) e as despesas comprovadas por documentos. A API
 * calcula a situacao de cada linha e o saldo de cada programa; o site so mostra.
 */

export type PddeProgram = "BASICO" | "EQUIDADE" | "QUALIDADE" | "CONECTADO" | "OUTRO";
export type PddeEconomic = "CUSTEIO" | "CAPITAL";
export type PddeKind = "TRANSFER" | "EXPENSE" | "TAX_TO_EEX" | "REFUND" | "INELIGIBLE";
export type PddeDocKind = "NFE" | "INVOICE" | "RECEIPT" | "OTHER";
export type PddeStatus = "PENDING" | "PARTIAL" | "DONE";
export type PddeAlertCode = "fee_on_pdde_account" | "pending_lines" | "spent_over_received" | "year_end_reconciliation" | "deadline" | "deadline_passed";

const PROGRAMS: readonly PddeProgram[] = ["BASICO", "EQUIDADE", "QUALIDADE", "CONECTADO", "OUTRO"];
const KINDS: readonly PddeKind[] = ["TRANSFER", "EXPENSE", "TAX_TO_EEX", "REFUND", "INELIGIBLE"];
const DOC_KINDS: readonly PddeDocKind[] = ["NFE", "INVOICE", "RECEIPT", "OTHER"];
const STATUSES: readonly PddeStatus[] = ["PENDING", "PARTIAL", "DONE"];
const ALERTS: readonly PddeAlertCode[] = ["fee_on_pdde_account", "pending_lines", "spent_over_received", "year_end_reconciliation", "deadline", "deadline_passed"];

export interface PddeDocument {
  id: string;
  docKind: PddeDocKind;
  accessKey: string | null;
  docNumber: string | null;
  issuedOn: string;
  vendor: string;
  amountCents: number;
  stamped: boolean;
  voided: boolean;
}

export interface PddeClassification {
  kind: PddeKind;
  program: PddeProgram | null;
  programLabel: string | null;
  economicCategory: PddeEconomic | null;
  object: string | null;
  note: string | null;
}

export interface PddeLine {
  lineId: string;
  accountId: string;
  accountNickname: string;
  postedOn: string;
  amountCents: number;
  memo: string;
  looksLikeFee: boolean;
  classification: PddeClassification | null;
  documents: PddeDocument[];
  documentedCents: number;
  status: PddeStatus;
}

export interface PddeAccount {
  id: string;
  nickname: string;
  bankName: string;
  accountLast4: string | null;
}

export interface PddeAlert {
  code: PddeAlertCode;
  count: number;
  cents: number;
  program: PddeProgram | null;
  economicCategory: PddeEconomic | null;
  date: string | null;
}

export interface PddeMonth {
  period: string;
  accounts: PddeAccount[];
  lines: PddeLine[];
  pendingCount: number;
  alerts: PddeAlert[];
}

export interface PddeProgramBalance {
  program: PddeProgram;
  programLabel: string | null;
  receivedCents: number;
  spentCusteioCents: number;
  spentCapitalCents: number;
  balanceCents: number;
}

export interface PddeYear {
  year: number;
  accounts: PddeAccount[];
  programs: PddeProgramBalance[];
  pendingCount: number;
  yearEnd: { accountId: string; accountNickname: string; balanceCents: number | null }[];
  alerts: PddeAlert[];
}

const enc = encodeURIComponent;
const school = (schoolId: string) => `/api/v1/schools/${enc(schoolId)}/pdde`;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
const int = (value: unknown): number | null => (typeof value === "number" && Number.isSafeInteger(value) ? value : null);
const str = (value: unknown): string | null => (typeof value === "string" ? value : null);
const oneOf = <T extends string>(list: readonly T[], value: unknown): T | null => (typeof value === "string" && (list as readonly string[]).includes(value) ? (value as T) : null);
const nullable = <T>(value: unknown, parse: (v: unknown) => T | null): T | null | undefined => (value === null || value === undefined ? null : (parse(value) ?? undefined));

function parseDocument(raw: unknown): PddeDocument | null {
  if (!isRecord(raw)) return null;
  const docKind = oneOf(DOC_KINDS, raw.doc_kind);
  const amountCents = int(raw.amount_cents);
  const id = str(raw.id);
  const issuedOn = str(raw.issued_on);
  const vendor = str(raw.vendor);
  if (!docKind || amountCents === null || !id || !issuedOn || !vendor) return null;
  if (typeof raw.stamped !== "boolean" || typeof raw.voided !== "boolean") return null;
  return { id, docKind, accessKey: str(raw.access_key), docNumber: str(raw.doc_number), issuedOn, vendor, amountCents, stamped: raw.stamped, voided: raw.voided };
}

function parseClassification(raw: unknown): PddeClassification | null | undefined {
  if (raw === null || raw === undefined) return null;
  if (!isRecord(raw)) return undefined;
  const kind = oneOf(KINDS, raw.kind);
  if (!kind) return undefined;
  const program = nullable(raw.program, (v) => oneOf(PROGRAMS, v));
  const economicCategory = nullable(raw.economic_category, (v) => oneOf(["CUSTEIO", "CAPITAL"] as const, v));
  if (program === undefined || economicCategory === undefined) return undefined;
  return { kind, program, programLabel: str(raw.program_label), economicCategory, object: str(raw.object), note: str(raw.note) };
}

function parseLine(raw: unknown): PddeLine | null {
  if (!isRecord(raw) || !Array.isArray(raw.documents)) return null;
  const lineId = str(raw.line_id);
  const accountId = str(raw.account_id);
  const accountNickname = str(raw.account_nickname);
  const postedOn = str(raw.posted_on);
  const memo = str(raw.memo);
  const amountCents = int(raw.amount_cents);
  const documentedCents = int(raw.documented_cents);
  const status = oneOf(STATUSES, raw.status);
  const classification = parseClassification(raw.classification);
  if (!lineId || !accountId || !accountNickname || !postedOn || memo === null || amountCents === null || documentedCents === null || !status || classification === undefined) return null;
  if (typeof raw.looks_like_fee !== "boolean") return null;
  const documents: PddeDocument[] = [];
  for (const d of raw.documents) {
    const parsed = parseDocument(d);
    if (!parsed) return null;
    documents.push(parsed);
  }
  return { lineId, accountId, accountNickname, postedOn, amountCents, memo, looksLikeFee: raw.looks_like_fee, classification, documents, documentedCents, status };
}

function parseAccount(raw: unknown): PddeAccount | null {
  if (!isRecord(raw)) return null;
  const id = str(raw.id);
  const nickname = str(raw.nickname);
  const bankName = str(raw.bank_name);
  if (!id || !nickname || !bankName) return null;
  return { id, nickname, bankName, accountLast4: str(raw.account_last4) };
}

function parseAlert(raw: unknown): PddeAlert | null {
  if (!isRecord(raw)) return null;
  const code = oneOf(ALERTS, raw.code);
  const count = int(raw.count);
  const cents = int(raw.cents);
  const program = nullable(raw.program, (v) => oneOf(PROGRAMS, v));
  const economicCategory = nullable(raw.economic_category, (v) => oneOf(["CUSTEIO", "CAPITAL"] as const, v));
  if (!code || count === null || cents === null || program === undefined || economicCategory === undefined) return null;
  return { code, count, cents, program, economicCategory, date: str(raw.date) };
}

function list<T>(value: unknown, parse: (raw: unknown) => T | null): T[] | null {
  if (!Array.isArray(value) || value.length > 5000) return null;
  const out: T[] = [];
  for (const raw of value) {
    const parsed = parse(raw);
    if (parsed === null) return null;
    out.push(parsed);
  }
  return out;
}

export function parseMonth(body: unknown): PddeMonth | null {
  if (!isRecord(body)) return null;
  const accounts = list(body.accounts, parseAccount);
  const lines = list(body.lines, parseLine);
  const alerts = list(body.alerts, parseAlert);
  const pendingCount = int(body.pending_count);
  if (typeof body.period !== "string" || !accounts || !lines || !alerts || pendingCount === null) return null;
  return { period: body.period, accounts, lines, pendingCount, alerts };
}

function parseBalance(raw: unknown): PddeProgramBalance | null {
  if (!isRecord(raw)) return null;
  const program = oneOf(PROGRAMS, raw.program);
  const receivedCents = int(raw.received_cents);
  const spentCusteioCents = int(raw.spent_custeio_cents);
  const spentCapitalCents = int(raw.spent_capital_cents);
  const balanceCents = int(raw.balance_cents);
  if (!program || receivedCents === null || spentCusteioCents === null || spentCapitalCents === null || balanceCents === null) return null;
  return { program, programLabel: str(raw.program_label), receivedCents, spentCusteioCents, spentCapitalCents, balanceCents };
}

export function parseYear(body: unknown): PddeYear | null {
  if (!isRecord(body)) return null;
  const year = int(body.year);
  const accounts = list(body.accounts, parseAccount);
  const programs = list(body.programs, parseBalance);
  const alerts = list(body.alerts, parseAlert);
  const pendingCount = int(body.pending_count);
  const yearEnd = list(body.year_end, (raw) => {
    if (!isRecord(raw)) return null;
    const accountId = str(raw.account_id);
    const accountNickname = str(raw.account_nickname);
    const balanceCents = raw.balance_cents === null ? null : int(raw.balance_cents);
    if (!accountId || !accountNickname || (raw.balance_cents !== null && balanceCents === null)) return null;
    return { accountId, accountNickname, balanceCents };
  });
  if (year === null || !accounts || !programs || !alerts || !yearEnd || pendingCount === null) return null;
  return { year, accounts, programs, pendingCount, yearEnd, alerts };
}

/** GET .../pdde/lines?period=: as linhas das contas do PDDE no mes. */
export function getPddeMonth(schoolId: string, period: string, options?: RequestOptions): Promise<ApiResult<PddeMonth>> {
  return apiGet(`${school(schoolId)}/lines?period=${enc(period)}`, (body, status) => (status === 200 ? parseMonth(body) : null), options);
}

/** GET .../pdde/summary?year=: o saldo de cada programa e o que pede atencao. */
export function getPddeYear(schoolId: string, year: number, options?: RequestOptions): Promise<ApiResult<PddeYear>> {
  return apiGet(`${school(schoolId)}/summary?year=${year}`, (body, status) => (status === 200 ? parseYear(body) : null), options);
}

export interface ClassificationInput {
  kind: PddeKind;
  program?: PddeProgram;
  programLabel?: string;
  economicCategory?: PddeEconomic;
  object?: string;
  note?: string;
}

const saved = (body: unknown, status: number) => (status === 201 && isRecord(body) ? { ok: true as const } : null);

/** POST .../pdde/lines/{id}/classification: uma nova decisao (vale a ultima). */
export function classifyPddeLine(schoolId: string, lineId: string, input: ClassificationInput, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  const body: Record<string, string> = { kind: input.kind };
  if (input.program) body.program = input.program;
  if (input.programLabel) body.program_label = input.programLabel;
  if (input.economicCategory) body.economic_category = input.economicCategory;
  if (input.object) body.object = input.object;
  if (input.note) body.note = input.note;
  return apiSend("POST", `${school(schoolId)}/lines/${enc(lineId)}/classification`, body, saved, options);
}

export interface DocumentInput {
  docKind: PddeDocKind;
  accessKey?: string;
  docNumber?: string;
  issuedOn: string;
  vendor: string;
  amountCents: number;
  stamped: boolean;
}

/** POST .../pdde/lines/{id}/documents: o documento que comprova a despesa. */
export function addPddeDocument(schoolId: string, lineId: string, input: DocumentInput, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  const body: Record<string, string | number | boolean> = {
    doc_kind: input.docKind,
    issued_on: input.issuedOn,
    vendor: input.vendor,
    amount_cents: input.amountCents,
    stamped: input.stamped,
  };
  if (input.accessKey) body.access_key = input.accessKey;
  if (input.docNumber) body.doc_number = input.docNumber;
  return apiSend("POST", `${school(schoolId)}/lines/${enc(lineId)}/documents`, body, saved, options);
}

/** POST .../pdde/documents/{id}/void: anula um documento errado (nunca apaga). */
export function voidPddeDocument(schoolId: string, documentId: string, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  return apiSend("POST", `${school(schoolId)}/documents/${enc(documentId)}/void`, {}, (body, status) => (status === 200 && isRecord(body) ? { ok: true as const } : null), options);
}

/** Links dos relatorios do ano (navegacoes, nao fetch). */
export function pddeReportHref(schoolId: string, year: number, format: "csv" | "pdf"): string {
  return `${school(schoolId)}/report.${format}?year=${year}`;
}
