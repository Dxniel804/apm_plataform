import { apiGet, apiSend, type RequestOptions, type SendOptions } from "./client";
import type { ApiResult } from "./types";

/**
 * O balancete do mes, no formato da folha da contadora (docs/statement.md). Os numeros sao os do livro
 * caixa, conferidos pela API contra o resumo do mes: o site nao soma nem recalcula. O que o livro nao
 * sabe (o saldo da escola no dia em que comecou, e o caixa e a aplicacao no fim de cada mes) a gestao digita.
 */

export interface BalanceteLine {
  name: string;
  cents: number;
}

export interface BalancetePlace {
  bankCents: number;
  cashCents: number;
  investmentCents: number;
  totalCents: number;
}

export interface Balancete {
  period: string;
  opening: BalancetePlace;
  revenue: BalanceteLine[];
  totalRevenueCents: number;
  capital: BalanceteLine[];
  totalCapitalCents: number;
  expenses: BalanceteLine[];
  totalExpensesCents: number;
  balanceOfMonthCents: number;
  closing: BalancetePlace;
  closingTyped: boolean;
  hasOpening: boolean;
}

const enc = encodeURIComponent;
const school = (schoolId: string) => `/api/v1/schools/${enc(schoolId)}`;
const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const int = (value: unknown): number | null => (typeof value === "number" && Number.isSafeInteger(value) ? value : null);

function parsePlace(value: unknown): BalancetePlace | null {
  if (!isRecord(value)) return null;
  const bankCents = int(value.bank_cents);
  const cashCents = int(value.cash_cents);
  const investmentCents = int(value.investment_cents);
  const totalCents = int(value.total_cents);
  if (bankCents === null || cashCents === null || investmentCents === null || totalCents === null) return null;
  return { bankCents, cashCents, investmentCents, totalCents };
}

function parseLines(value: unknown): BalanceteLine[] | null {
  if (!Array.isArray(value) || value.length > 100) return null;
  const out: BalanceteLine[] = [];
  for (const raw of value) {
    if (!isRecord(raw) || typeof raw.name !== "string" || raw.name.length === 0 || raw.name.length > 200) return null;
    const cents = int(raw.cents);
    if (cents === null) return null;
    out.push({ name: raw.name, cents });
  }
  return out;
}

export function parseBalancete(body: unknown): Balancete | null {
  if (!isRecord(body)) return null;
  const opening = parsePlace(body.opening);
  const closing = parsePlace(body.closing);
  const revenue = parseLines(body.revenue);
  const capital = parseLines(body.capital);
  const expenses = parseLines(body.expenses);
  const totalRevenueCents = int(body.total_revenue_cents);
  const totalCapitalCents = int(body.total_capital_cents);
  const totalExpensesCents = int(body.total_expenses_cents);
  const balanceOfMonthCents = int(body.balance_of_month_cents);
  if (typeof body.period !== "string" || !PERIOD_RE.test(body.period)) return null;
  if (typeof body.closing_typed !== "boolean" || typeof body.has_opening !== "boolean") return null;
  if (!opening || !closing || !revenue || !capital || !expenses) return null;
  if (totalRevenueCents === null || totalCapitalCents === null || totalExpensesCents === null || balanceOfMonthCents === null) return null;
  return {
    period: body.period,
    opening,
    revenue,
    totalRevenueCents,
    capital,
    totalCapitalCents,
    expenses,
    totalExpensesCents,
    balanceOfMonthCents,
    closing,
    closingTyped: body.closing_typed,
    hasOpening: body.has_opening,
  };
}

/** GET .../balancete. */
export function getBalancete(schoolId: string, period: string, options?: RequestOptions): Promise<ApiResult<Balancete>> {
  return apiGet(`${school(schoolId)}/balancete?period=${enc(period)}`, (body, status) => (status === 200 ? parseBalancete(body) : null), options);
}

/** Link do PDF do balancete (GET .../balancete.pdf). E uma navegacao, nao um fetch. */
export function balancetePdfHref(schoolId: string, period: string): string {
  return `${school(schoolId)}/balancete.pdf?period=${enc(period)}`;
}

export type BalanceInput =
  | { kind: "OPENING"; bankCents: number; cashCents: number; investmentCents: number }
  | { kind: "MONTH"; period: string; cashCents: number; investmentCents: number };

/** POST .../balancete/balances (`months:close`). So insere: corrigir e digitar de novo, vale o ultimo. */
export function setBalance(schoolId: string, input: BalanceInput, options: SendOptions = {}): Promise<ApiResult<{ status: string }>> {
  const body: Record<string, string | number> =
    input.kind === "OPENING"
      ? { kind: "OPENING", bank_cents: input.bankCents, cash_cents: input.cashCents, investment_cents: input.investmentCents }
      : { kind: "MONTH", period: input.period, cash_cents: input.cashCents, investment_cents: input.investmentCents };
  return apiSend("POST", `${school(schoolId)}/balancete/balances`, body, (data, status) => (status === 201 && isRecord(data) && data.status === "saved" ? { status: "saved" } : null), options);
}
