import { describe, expect, it } from "vitest";
import { parseRules, parseTaxMonth } from "./tax";

const rule = (over: Record<string, unknown> = {}) => ({ id: "r1", rule_key: "irrf-servicos-pj", label: "IRRF", tax_kind: "IRRF", applies_to: "PJ", rate_bps: 150, base_cap_cents: null, min_total_cents: 1000, darf_code: "1708", howto: null, due_day: 20, due_roll: "PREVIOUS", source_note: null, validated: false, validated_at: null, ...over });
const suggestion = (over: Record<string, unknown> = {}) => ({ rule_key: "iss-municipal", label: "ISS", tax_kind: "ISS", applies_to: "BOTH", rate_bps: null, base_cap_cents: null, darf_code: null, howto: "Guia da prefeitura", warning: "NÃO validada", ...over });
const guide = (over: Record<string, unknown> = {}) => ({ rule_key: "irrf-servicos-pj", label: "IRRF", tax_kind: "IRRF", darf_code: "1708", howto: null, competence: "2026-10", due_date: "2026-11-20", total_cents: 4500, count: 2, min_total_cents: 1000, below_minimum: false, validated: true, mixed_versions: false, site_url: "https://exemplo.gov.br", ...over });
const retention = (over: Record<string, unknown> = {}) => ({ id: "t1", rule_key: "irrf-servicos-pj", rule_label: "IRRF", provider_kind: "PJ", provider_name: "Pintura", competence: "2026-10", gross_cents: 100_000, base_cents: 100_000, retained_cents: 1500, net_cents: 98_500, rate_bps: 150, note: null, voided: false, validated: true, ...over });

describe("parseRules", () => {
  it("le as regras e as sugestoes (que podem ficar sem aliquota)", () => {
    const r = parseRules({ rules: [rule()], suggestions: [suggestion()] });
    expect(r?.rules[0]?.darfCode).toBe("1708");
    expect(r?.rules[0]?.validated).toBe(false);
    expect(r?.suggestions[0]?.rateBps).toBeNull();
  });
  it("recusa o torto", () => {
    expect(parseRules({ rules: [rule({ tax_kind: "VAT" })], suggestions: [] })).toBeNull();
    expect(parseRules({ rules: [rule({ rate_bps: 1.5 })], suggestions: [] })).toBeNull();
    expect(parseRules({ rules: [rule({ validated: "yes" })], suggestions: [] })).toBeNull();
    expect(parseRules({ rules: [], suggestions: [suggestion({ warning: null })] })).toBeNull();
    expect(parseRules(null)).toBeNull();
  });
});

describe("parseTaxMonth", () => {
  it("le as guias e as retencoes do mes", () => {
    const m = parseTaxMonth({ period: "2026-10", retentions: [retention()], guides: [guide()] });
    expect(m?.guides[0]?.dueDate).toBe("2026-11-20");
    expect(m?.guides[0]?.belowMinimum).toBe(false);
    expect(m?.retentions[0]?.netCents).toBe(98_500);
  });
  it("recusa valor que nao e inteiro e flag que nao e booleano", () => {
    expect(parseTaxMonth({ period: "2026-10", retentions: [], guides: [guide({ total_cents: 45.5 })] })).toBeNull();
    expect(parseTaxMonth({ period: "2026-10", retentions: [], guides: [guide({ validated: 1 })] })).toBeNull();
    expect(parseTaxMonth({ period: "2026-10", retentions: [retention({ voided: null })], guides: [] })).toBeNull();
  });
});
