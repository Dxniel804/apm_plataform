import { apiGet, apiSend, type RequestOptions, type SendOptions } from "./client";
import type { ApiResult } from "./types";

/**
 * PDDE: a prestacao de contas do dinheiro federal (docs/m8-pdde-plan.md). A conta bancaria do PDDE tem as suas
 * linhas classificadas (programa, custeio ou capital, objeto) e as despesas comprovadas por documentos. A API
 * calcula a situacao de cada linha e o saldo de cada programa; o site so mostra.
 */

export type PddeProgram = "BASICO" | "EQUIDADE" | "QUALIDADE" | "CONECTADO" | "OUTRO";
export type PddeEconomic = "CUSTEIO" | "CAPITAL";
export type PddeKind = "TRANSFER" | "YIELD" | "EXPENSE" | "RETURN_TO_FNDE" | "TAX_TO_EEX" | "REFUND" | "INELIGIBLE";
export type PddeDocKind = "NFE" | "INVOICE" | "RECEIPT" | "OTHER";
export type PddeStatus = "PENDING" | "PARTIAL" | "DONE";
export type PddeAlertCode = "fee_on_pdde_account" | "pending_lines" | "spent_over_received" | "year_end_reconciliation" | "deadline" | "deadline_passed";

const PROGRAMS: readonly PddeProgram[] = ["BASICO", "EQUIDADE", "QUALIDADE", "CONECTADO", "OUTRO"];
const KINDS: readonly PddeKind[] = ["TRANSFER", "YIELD", "EXPENSE", "RETURN_TO_FNDE", "TAX_TO_EEX", "REFUND", "INELIGIBLE"];
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
  vendorTaxId: string | null;
  quantity: number | null;
  specification: string | null;
}

export interface PddeClassification {
  kind: PddeKind;
  program: PddeProgram | null;
  programLabel: string | null;
  economicCategory: PddeEconomic | null;
  object: string | null;
  note: string | null;
  paymentNumber: string | null;
}

/** A despesa (decidida como PDDE) que esta saida do extrato paga, achada por valor e data. A categoria diz o que foi e se e custeio ou capital. */
export interface PddeExpenseLink {
  expenseId: string;
  referenceCode: number;
  description: string;
  categoryKey: string;
  categoryName: string;
  economicNature: PddeEconomic | null;
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
  /** So na visao do mes. */
  expense: PddeExpenseLink | null;
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

/** O que o banco diz que a conta do PDDE guarda, pelo ultimo extrato ate o fim do mes (null: nenhum extrato com saldo). */
export interface PddeBankBalance {
  accountId: string;
  accountNickname: string;
  balanceCents: number | null;
  asOf: string | null;
}

export interface PddeMonth {
  period: string;
  accounts: PddeAccount[];
  bankBalances: PddeBankBalance[];
  lines: PddeLine[];
  pendingCount: number;
  alerts: PddeAlert[];
}

export interface PddeProgramBalance {
  program: PddeProgram;
  programLabel: string | null;
  receivedCents: number;
  yieldCents: number;
  returnedCents: number;
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
const nint = (value: unknown): number | null | undefined => (value === null || value === undefined ? null : (int(value) ?? undefined));
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
  const quantity = nint(raw.quantity);
  if (quantity === undefined) return null;
  return { id, docKind, accessKey: str(raw.access_key), docNumber: str(raw.doc_number), issuedOn, vendor, amountCents, stamped: raw.stamped, voided: raw.voided, vendorTaxId: str(raw.vendor_tax_id), quantity, specification: str(raw.specification) };
}

function parseClassification(raw: unknown): PddeClassification | null | undefined {
  if (raw === null || raw === undefined) return null;
  if (!isRecord(raw)) return undefined;
  const kind = oneOf(KINDS, raw.kind);
  if (!kind) return undefined;
  const program = nullable(raw.program, (v) => oneOf(PROGRAMS, v));
  const economicCategory = nullable(raw.economic_category, (v) => oneOf(["CUSTEIO", "CAPITAL"] as const, v));
  if (program === undefined || economicCategory === undefined) return undefined;
  return { kind, program, programLabel: str(raw.program_label), economicCategory, object: str(raw.object), note: str(raw.note), paymentNumber: str(raw.payment_number) };
}

function parseExpenseLink(raw: unknown): PddeExpenseLink | null | undefined {
  if (raw === null || raw === undefined) return null;
  if (!isRecord(raw)) return undefined;
  const expenseId = str(raw.expense_id);
  const referenceCode = int(raw.reference_code);
  const categoryKey = str(raw.category_key);
  const categoryName = str(raw.category_name);
  const economicNature = nullable(raw.economic_nature, (v) => oneOf(["CUSTEIO", "CAPITAL"] as const, v));
  if (!expenseId || referenceCode === null || !categoryKey || !categoryName || typeof raw.description !== "string" || economicNature === undefined) return undefined;
  return { expenseId, referenceCode, description: raw.description, categoryKey, categoryName, economicNature };
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
  const expense = parseExpenseLink(raw.expense);
  if (expense === undefined) return null;
  return { lineId, accountId, accountNickname, postedOn, amountCents, memo, looksLikeFee: raw.looks_like_fee, classification, documents, documentedCents, status, expense };
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

function parseBankBalance(raw: unknown): PddeBankBalance | null {
  if (!isRecord(raw)) return null;
  const accountId = str(raw.account_id);
  const accountNickname = str(raw.account_nickname);
  const balanceCents = raw.balance_cents === null || raw.balance_cents === undefined ? null : int(raw.balance_cents);
  if (!accountId || !accountNickname || (raw.balance_cents != null && balanceCents === null)) return null;
  return { accountId, accountNickname, balanceCents, asOf: str(raw.as_of) };
}

export function parseMonth(body: unknown): PddeMonth | null {
  if (!isRecord(body)) return null;
  const accounts = list(body.accounts, parseAccount);
  const bankBalances = body.bank_balances === undefined ? [] : list(body.bank_balances, parseBankBalance);
  const lines = list(body.lines, parseLine);
  const alerts = list(body.alerts, parseAlert);
  const pendingCount = int(body.pending_count);
  if (typeof body.period !== "string" || !accounts || !bankBalances || !lines || !alerts || pendingCount === null) return null;
  return { period: body.period, accounts, bankBalances, lines, pendingCount, alerts };
}

function parseBalance(raw: unknown): PddeProgramBalance | null {
  if (!isRecord(raw)) return null;
  const program = oneOf(PROGRAMS, raw.program);
  const receivedCents = int(raw.received_cents);
  const spentCusteioCents = int(raw.spent_custeio_cents);
  const spentCapitalCents = int(raw.spent_capital_cents);
  const balanceCents = int(raw.balance_cents);
  if (!program || receivedCents === null || spentCusteioCents === null || spentCapitalCents === null || balanceCents === null) return null;
  const yieldCents = int(raw.yield_cents ?? 0);
  const returnedCents = int(raw.returned_cents ?? 0);
  if (yieldCents === null || returnedCents === null) return null;
  return { program, programLabel: str(raw.program_label), receivedCents, yieldCents, returnedCents, spentCusteioCents, spentCapitalCents, balanceCents };
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
  paymentNumber?: string;
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
  if (input.paymentNumber) body.payment_number = input.paymentNumber;
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
  vendorTaxId?: string;
  quantity?: number;
  specification?: string;
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
  if (input.vendorTaxId) body.vendor_tax_id = input.vendorTaxId;
  if (input.quantity) body.quantity = input.quantity;
  if (input.specification) body.specification = input.specification;
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

// --- the entity, the carry-over and the official form ------------------------------------------------

export interface PddeEntity {
  legalName: string;
  cnpj: string;
  address: string;
  city: string;
  state: string;
}

export function parseEntity(body: unknown): PddeEntity | null | undefined {
  if (body === null) return null;
  if (!isRecord(body)) return undefined;
  const legalName = str(body.legal_name);
  const cnpj = str(body.cnpj);
  const address = str(body.address);
  const city = str(body.city);
  const state = str(body.state);
  return legalName && cnpj && address && city && state ? { legalName, cnpj, address, city, state } : undefined;
}

/** GET .../pdde/entity: o nome, o CNPJ e o endereco que saem no formulario (null: ainda nao informados). */
export function getPddeEntity(schoolId: string, options?: RequestOptions): Promise<ApiResult<PddeEntity | null>> {
  return apiGet(`${school(schoolId)}/entity`, (body, status) => {
    if (status !== 200) return null;
    const parsed = parseEntity(body);
    return parsed === undefined ? null : parsed;
  }, options) as Promise<ApiResult<PddeEntity | null>>;
}

export function savePddeEntity(schoolId: string, input: PddeEntity, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  const body = { legal_name: input.legalName, cnpj: input.cnpj, address: input.address, city: input.city, state: input.state };
  return apiSend("POST", `${school(schoolId)}/entity`, body, saved, options);
}

export interface PddeCarryover {
  program: PddeProgram;
  programLabel: string | null;
  custeioCents: number;
  capitalCents: number;
}

export function parseCarryovers(body: unknown): PddeCarryover[] | null {
  return list(body, (raw) => {
    if (!isRecord(raw)) return null;
    const program = oneOf(PROGRAMS, raw.program);
    const custeioCents = int(raw.custeio_cents);
    const capitalCents = int(raw.capital_cents);
    return program && custeioCents !== null && capitalCents !== null ? { program, programLabel: str(raw.program_label), custeioCents, capitalCents } : null;
  });
}

/** GET .../pdde/carryovers?year=: o saldo do ano anterior que a escola digitou. */
export function getPddeCarryovers(schoolId: string, year: number, options?: RequestOptions): Promise<ApiResult<PddeCarryover[]>> {
  return apiGet(`${school(schoolId)}/carryovers?year=${year}`, (body, status) => (status === 200 ? parseCarryovers(body) : null), options);
}

export function savePddeCarryover(schoolId: string, year: number, input: PddeCarryover, options: SendOptions = {}): Promise<ApiResult<{ ok: true }>> {
  const body: Record<string, string | number> = { year, program: input.program, custeio_cents: input.custeioCents, capital_cents: input.capitalCents };
  if (input.programLabel) body.program_label = input.programLabel;
  return apiSend("POST", `${school(schoolId)}/carryovers`, body, saved, options);
}

/** Link da Relacao de bens adquiridos ou produzidos (formulario do FNDE), um por programa e ano. */
export function pddeBensHref(schoolId: string, year: number, program: PddeProgram, programLabel: string | null): string {
  return `${school(schoolId)}/forms/bens.pdf?year=${year}&program=${program}${programLabel ? `&program_label=${enc(programLabel)}` : ""}`;
}

/** Link da Conciliacao bancaria (formulario do FNDE), uma por conta do PDDE e ano. */
export function pddeConciliacaoHref(schoolId: string, year: number, accountId: string): string {
  return `${school(schoolId)}/forms/conciliacao.pdf?year=${year}&account_id=${enc(accountId)}`;
}

/** Link do formulario oficial do FNDE (Demonstrativo), um por programa e ano (navegacao, nao fetch). */
export function pddeDemonstrativoHref(schoolId: string, year: number, program: PddeProgram, programLabel: string | null): string {
  return `${school(schoolId)}/forms/demonstrativo.pdf?year=${year}&program=${program}${programLabel ? `&program_label=${enc(programLabel)}` : ""}`;
}
