import { apiGet, apiSend, apiUpload, type RequestOptions, type SendOptions } from "./client";
import type { AccountPurpose, ApiResult, BankAccount, BankAccountInput, BankLine, Divergence, LedgerEntry, Reconciliation, StatementImport } from "./types";

/**
 * Conciliacao bancaria (migracao 0017): as contas da escola, o envio do extrato OFX e a comparacao com o caixa.
 * Nada aqui grava no caixa. O site so mostra e envia; quem le o arquivo e decide o pareamento e a API.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
const int = (v: unknown): number | null => (typeof v === "number" && Number.isSafeInteger(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const optStr = (v: unknown): string | null | undefined => (v === null || v === undefined ? null : typeof v === "string" ? v : undefined);
const PURPOSES: readonly AccountPurpose[] = ["GENERAL", "PDDE"];

function parseAccount(v: unknown): BankAccount | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const nickname = str(v.nickname);
  const bankName = str(v.bank_name);
  const last4 = optStr(v.account_last4);
  const purpose = PURPOSES.find((p) => p === v.purpose);
  if (!id || !nickname || !bankName || last4 === undefined || !purpose || typeof v.is_active !== "boolean") return null;
  return { id, nickname, bankName, accountLast4: last4, purpose, isActive: v.is_active };
}

export function parseImport(v: unknown): StatementImport | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const bankAccountId = str(v.bank_account_id);
  const periodStart = str(v.period_start);
  const periodEnd = str(v.period_end);
  const lineCount = int(v.line_count);
  const newLineCount = int(v.new_line_count);
  const createdAt = str(v.created_at);
  const closing = v.closing_balance_cents === null || v.closing_balance_cents === undefined ? null : int(v.closing_balance_cents);
  if (!id || !bankAccountId || !periodStart || !periodEnd || lineCount === null || newLineCount === null || !createdAt) return null;
  if (v.closing_balance_cents != null && closing === null) return null;
  return { id, bankAccountId, periodStart, periodEnd, lineCount, newLineCount, closingBalanceCents: closing, createdAt };
}

function parseLine(v: unknown): BankLine | null {
  if (!isRecord(v)) return null;
  const lineId = str(v.line_id);
  const postedOn = str(v.posted_on);
  const amountCents = int(v.amount_cents);
  const e2e = optStr(v.end_to_end_id);
  if (!lineId || !postedOn || amountCents === null || typeof v.memo !== "string" || e2e === undefined || typeof v.looks_like_fee !== "boolean") return null;
  return { lineId, postedOn, amountCents, memo: v.memo, endToEndId: e2e, looksLikeFee: v.looks_like_fee };
}

function parseEntry(v: unknown): LedgerEntry | null {
  if (!isRecord(v)) return null;
  const transactionId = str(v.transaction_id);
  const referenceCode = int(v.reference_code);
  const kind = str(v.kind);
  const day = str(v.day);
  const amountCents = int(v.amount_cents);
  const net = v.net_cents === null || v.net_cents === undefined ? null : int(v.net_cents);
  if (!transactionId || referenceCode === null || !kind || !day || amountCents === null || (v.net_cents != null && net === null)) return null;
  return { transactionId, referenceCode, kind, day, amountCents, netCents: net };
}

function parseList<T>(raw: unknown, one: (v: unknown) => T | null): T[] | null {
  if (!Array.isArray(raw)) return null;
  const out: T[] = [];
  for (const item of raw) {
    const parsed = one(item);
    if (!parsed) return null;
    out.push(parsed);
  }
  return out;
}

export function parseReconciliation(body: unknown): Reconciliation | null {
  if (!isRecord(body)) return null;
  const statement = parseImport(body.statement);
  const matchedRaw = parseList(body.matched, (m) => {
    if (!isRecord(m)) return null;
    const line = parseLine(m.line);
    const entry = parseEntry(m.entry);
    return line && entry ? { line, entry } : null;
  });
  const missingInSystem = parseList(body.missing_in_system, parseLine);
  const missingInBank = parseList(body.missing_in_bank, parseEntry);
  const divergences = parseList<Divergence>(body.divergences, (d) => {
    if (!isRecord(d)) return null;
    const line = parseLine(d.line);
    const candidates = parseList(d.candidates, parseEntry);
    const reason = d.reason === "ambiguous" || d.reason === "amount_differs" ? d.reason : null;
    return line && candidates && reason ? { line, candidates, reason } : null;
  });
  if (!statement || !matchedRaw || !missingInSystem || !missingInBank || !divergences) return null;
  return { statement, matched: matchedRaw, missingInSystem, missingInBank, divergences };
}

const base = (schoolId: string) => `/api/v1/schools/${encodeURIComponent(schoolId)}/reconciliation`;

export function listBankAccounts(schoolId: string, options?: RequestOptions): Promise<ApiResult<BankAccount[]>> {
  return apiGet(`${base(schoolId)}/accounts`, (body, status) => (status === 200 ? parseList(body, parseAccount) : null), options);
}

export function createBankAccount(schoolId: string, input: BankAccountInput, options?: SendOptions): Promise<ApiResult<BankAccount>> {
  const body: Record<string, unknown> = { nickname: input.nickname, bank_name: input.bankName };
  if (input.accountLast4) body.account_last4 = input.accountLast4;
  if (input.purpose) body.purpose = input.purpose;
  return apiSend("POST", `${base(schoolId)}/accounts`, body, (b, status) => (status === 201 ? parseAccount(b) : null), options);
}

export function setBankAccountActive(schoolId: string, accountId: string, isActive: boolean, options?: SendOptions): Promise<ApiResult<BankAccount>> {
  return apiSend("PATCH", `${base(schoolId)}/accounts/${encodeURIComponent(accountId)}`, { is_active: isActive }, (b, status) => (status === 200 ? parseAccount(b) : null), options);
}

export function listStatementImports(schoolId: string, options?: RequestOptions): Promise<ApiResult<StatementImport[]>> {
  return apiGet(
    `${base(schoolId)}/imports`,
    (body, status) => (status === 200 && isRecord(body) ? parseList(body.items, parseImport) : null),
    options,
  );
}

/** POST multipart: o arquivo OFX vai so no corpo. A API le, mascara CPF e CNPJ do texto e nao guarda o arquivo. */
export function importStatement(schoolId: string, accountId: string, file: File, options?: SendOptions): Promise<ApiResult<StatementImport>> {
  const form = new FormData();
  form.append("bank_account_id", accountId);
  form.append("file", file, file.name);
  return apiUpload(`${base(schoolId)}/imports`, form, (b, status) => (status === 201 ? parseImport(b) : null), options);
}

export function getReconciliation(schoolId: string, importId: string, options?: RequestOptions): Promise<ApiResult<Reconciliation>> {
  return apiGet(`${base(schoolId)}/imports/${encodeURIComponent(importId)}`, (body, status) => (status === 200 ? parseReconciliation(body) : null), options);
}
