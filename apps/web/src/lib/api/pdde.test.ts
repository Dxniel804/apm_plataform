import { describe, expect, it } from "vitest";
import { parseMonth, parseYear, pddeReportHref } from "./pdde";

const doc = (over: Record<string, unknown> = {}) => ({ id: "d1", doc_kind: "NFE", access_key: "1".repeat(44), doc_number: null, issued_on: "2025-03-19", vendor: "Papelaria", amount_cents: 100_000, stamped: true, voided: false, ...over });
const line = (over: Record<string, unknown> = {}) => ({
  line_id: "l1",
  account_id: "a1",
  account_nickname: "PDDE",
  posted_on: "2025-03-20",
  amount_cents: -150_000,
  memo: "PAGAMENTO MATERIAL",
  looks_like_fee: false,
  classification: { kind: "EXPENSE", program: "BASICO", program_label: null, economic_category: "CAPITAL", object: "Material permanente", note: null },
  documents: [doc()],
  documented_cents: 100_000,
  status: "PARTIAL",
  ...over,
});
const month = (over: Record<string, unknown> = {}) => ({
  period: "2025-03",
  accounts: [{ id: "a1", nickname: "PDDE", bank_name: "Banco do Brasil", account_last4: null }],
  lines: [line()],
  pending_count: 1,
  alerts: [{ code: "pending_lines", count: 1, cents: 0, program: null, economic_category: null, date: null }],
  ...over,
});

describe("parseMonth", () => {
  it("le o mes como a API o manda", () => {
    const m = parseMonth(month());
    expect(m?.lines[0]?.classification?.economicCategory).toBe("CAPITAL");
    expect(m?.lines[0]?.documents[0]?.accessKey).toBe("1".repeat(44));
    expect(m?.lines[0]?.status).toBe("PARTIAL");
    expect(m?.alerts[0]?.code).toBe("pending_lines");
  });

  it("uma linha sem classificacao e valida; o resto torto e recusado", () => {
    expect(parseMonth(month({ lines: [line({ classification: null, documents: [], documented_cents: 0, status: "PENDING" })] }))?.lines[0]?.classification).toBeNull();
    expect(parseMonth(month({ lines: [line({ status: "DONE?" })] }))).toBeNull();
    expect(parseMonth(month({ lines: [line({ amount_cents: 1.5 })] }))).toBeNull();
    expect(parseMonth(month({ lines: [line({ documents: [doc({ doc_kind: "PDF" })] })] }))).toBeNull();
    expect(parseMonth(month({ alerts: [{ code: "boom", count: 1, cents: 0, program: null, economic_category: null, date: null }] }))).toBeNull();
    expect(parseMonth(null)).toBeNull();
  });
});

describe("parseYear", () => {
  it("le os saldos e o saldo de 31/12 (que pode faltar)", () => {
    const y = parseYear({
      year: 2025,
      accounts: [],
      programs: [{ program: "BASICO", program_label: null, received_cents: 1_000_000, spent_custeio_cents: 0, spent_capital_cents: 150_000, balance_cents: 850_000 }],
      pending_count: 0,
      year_end: [{ account_id: "a1", account_nickname: "PDDE", balance_cents: null }],
      alerts: [],
    });
    expect(y?.programs[0]?.balanceCents).toBe(850_000);
    expect(y?.yearEnd[0]?.balanceCents).toBeNull();
  });

  it("recusa saldo que nao e inteiro", () => {
    expect(parseYear({ year: 2025, accounts: [], programs: [], pending_count: 0, year_end: [{ account_id: "a", account_nickname: "P", balance_cents: "x" }], alerts: [] })).toBeNull();
  });
});

describe("pddeReportHref", () => {
  it("e uma navegacao para o relatorio do ano", () => {
    expect(pddeReportHref("a b", 2025, "pdf")).toBe("/api/v1/schools/a%20b/pdde/report.pdf?year=2025");
  });
});
