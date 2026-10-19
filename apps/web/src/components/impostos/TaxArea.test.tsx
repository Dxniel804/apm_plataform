import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseRules, parseTaxMonth, type TaxMonth, type TaxRules } from "@/lib/api/tax";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { TaxArea } from "./TaxArea";

const rule = (over: Record<string, unknown> = {}) => ({ id: "r1", rule_key: "irrf-servicos-pj", label: "IRRF serviços", tax_kind: "IRRF", applies_to: "PJ", rate_bps: 150, base_cap_cents: null, min_total_cents: 1000, darf_code: "1708", howto: null, due_day: 20, due_roll: "PREVIOUS", source_note: null, validated: false, validated_at: null, ...over });
const suggestion = { rule_key: "iss-municipal", label: "ISS retido (prefeitura)", tax_kind: "ISS", applies_to: "BOTH", rate_bps: null, base_cap_cents: null, darf_code: null, howto: "Guia da prefeitura", warning: "Sugestão de partida, NÃO validada." };
const rules = (list: unknown[] = []) => parseRules({ rules: list, suggestions: [suggestion] }) as TaxRules;
const guide = (over: Record<string, unknown> = {}) => ({ rule_key: "irrf-servicos-pj", label: "IRRF serviços", tax_kind: "IRRF", darf_code: "1708", howto: null, competence: "2026-10", due_date: "2026-11-20", total_cents: 4500, count: 2, min_total_cents: 1000, below_minimum: false, validated: false, mixed_versions: false, site_url: "https://sicalc.exemplo.gov.br", ...over });
const month = (guides: unknown[] = [], retentions: unknown[] = []) => parseTaxMonth({ period: "2026-10", retentions, guides }) as TaxMonth;

afterEach(() => vi.restoreAllMocks());

function setup(r: TaxRules, m: TaxMonth) {
  vi.spyOn(api.tax, "rules").mockResolvedValue({ ok: true, data: r });
  vi.spyOn(api.tax, "month").mockResolvedValue({ ok: true, data: m });
  render(<TaxArea schoolId={SCHOOL_ID} />);
  return userEvent.setup();
}

describe("TaxArea", () => {
  it("sem regras, oferece sugestoes NAO validadas e nao deixa registrar retencao", async () => {
    setup(rules(), month());

    expect(await screen.findByText(/Nenhuma regra ainda/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sugestão: ISS retido/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Registrar uma retenção" })).toBeNull();
  });

  it("mostra a cola da guia: valor, vencimento, codigo, periodo e o aviso de regra nao validada", async () => {
    setup(rules([rule()]), month([guide()]));

    const card = await screen.findByTestId("guide-irrf-servicos-pj");
    expect(card).toHaveTextContent("R$ 45,00");
    expect(card).toHaveTextContent("1708");
    expect(card).toHaveTextContent("outubro de 2026");
    expect(card).toHaveTextContent("A regra ainda não foi validada pela contadora");
    expect(within(card).getByRole("link", { name: /Abrir o site da Receita/ })).toHaveAttribute("href", "https://sicalc.exemplo.gov.br");
    expect(within(card).getByRole("link", { name: /Abrir o site da Receita/ })).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("uma regra validada nao mostra o aviso, e abaixo do minimo manda somar ao mes seguinte", async () => {
    setup(rules([rule({ validated: true, validated_at: "2026-10-19T12:00:00Z" })]), month([guide({ validated: true, below_minimum: true, total_cents: 450 })]));

    const card = await screen.findByTestId("guide-irrf-servicos-pj");
    expect(card).not.toHaveTextContent("ainda não foi validada");
    expect(card).toHaveTextContent("abaixo do mínimo");
    expect(await screen.findByText(/Validada pela contadora/)).toBeInTheDocument();
  });

  it("salva uma regra pela sugestao: aliquota e vencimento vem de quem digita, e a validacao so se marcada", async () => {
    const save = vi.spyOn(api.tax, "saveRule").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(rules(), month());
    await user.click(await screen.findByRole("button", { name: /Sugestão: ISS retido/ }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("NÃO validada");

    await user.click(within(dialog).getByRole("button", { name: "Salvar a regra" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Informe a alíquota");
    expect(save).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText("Alíquota (%)"), "5");
    await user.type(within(dialog).getByLabelText("Dia do vencimento (no mês seguinte)"), "10");
    await user.click(within(dialog).getByRole("button", { name: "Salvar a regra" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0]![1]).toMatchObject({ ruleKey: "iss-municipal", rateBps: 500, dueDay: 10, taxKind: "ISS", validated: false });
  });

  it("registra uma retencao e mostra o calculo antes de salvar", async () => {
    vi.spyOn(api.tax, "preview").mockResolvedValue({ ok: true, data: { baseCents: 100_000, retainedCents: 1500, netCents: 98_500, rateBps: 150 } });
    const add = vi.spyOn(api.tax, "addRetention").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(rules([rule()]), month());
    await user.click(await screen.findByRole("button", { name: "Registrar uma retenção" }));
    const dialog = await screen.findByRole("dialog");

    await user.type(within(dialog).getByLabelText("Nome de quem recebeu"), "Pintura Exemplo");
    await user.type(within(dialog).getByLabelText("Valor do serviço (bruto)"), "100000");
    expect(await within(dialog).findByRole("status")).toHaveTextContent("Retido: R$ 15,00");
    await user.click(within(dialog).getByRole("button", { name: "Registrar" }));

    await waitFor(() => expect(add).toHaveBeenCalledTimes(1));
    expect(add.mock.calls[0]![1]).toMatchObject({ ruleId: "r1", providerKind: "PJ", providerName: "Pintura Exemplo", grossCents: 100_000 });
  });

  it("anula uma retencao e uma recusa vira texto sem o codigo", async () => {
    const voided = vi.spyOn(api.tax, "voidRetention").mockResolvedValue({ ok: false, error: { kind: "problem", status: 404, code: "not_found" } });
    const user = setup(
      rules([rule()]),
      month([], [{ id: "t1", rule_key: "irrf-servicos-pj", rule_label: "IRRF serviços", provider_kind: "PJ", provider_name: "Pintura Exemplo", competence: "2026-10", gross_cents: 100_000, base_cents: 100_000, retained_cents: 1500, net_cents: 98_500, rate_bps: 150, note: null, voided: false, validated: false }]),
    );

    await user.click(await screen.findByRole("button", { name: "Anular a retenção de Pintura Exemplo" }));

    expect(voided).toHaveBeenCalledWith(SCHOOL_ID, "t1");
    expect(await screen.findByRole("alert")).toHaveTextContent("Isto não está mais aqui");
    expect(screen.queryByText(/not_found/)).toBeNull();
  });
});
