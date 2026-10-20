import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseMonth, parseYear, type PddeMonth, type PddeYear } from "@/lib/api/pdde";
import type { ApiResult } from "@/lib/api/types";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { PddeArea } from "./PddeArea";

const line = (over: Record<string, unknown> = {}) => ({
  line_id: "l-debit",
  account_id: "a1",
  account_nickname: "PDDE",
  posted_on: "2025-03-20",
  amount_cents: -150_000,
  memo: "PAGAMENTO MATERIAL ESCOLAR",
  looks_like_fee: false,
  classification: null,
  documents: [],
  documented_cents: 0,
  status: "PENDING",
  ...over,
});
const month = (lines: unknown[], over: Record<string, unknown> = {}) =>
  parseMonth({
    period: "2025-03",
    accounts: [{ id: "a1", nickname: "PDDE", bank_name: "Banco do Brasil", account_last4: null }],
    lines,
    pending_count: lines.length,
    alerts: [],
    ...over,
  }) as PddeMonth;
const year = (over: Record<string, unknown> = {}) =>
  parseYear({ year: 2025, accounts: [], programs: [], pending_count: 1, year_end: [], alerts: [], ...over }) as PddeYear;
const ok = <T,>(data: T): ApiResult<T> => ({ ok: true, data });

afterEach(() => vi.restoreAllMocks());

function setup(m: PddeMonth, y: PddeYear = year()) {
  vi.spyOn(api.pdde, "month").mockResolvedValue(ok(m));
  vi.spyOn(api.pdde, "year").mockResolvedValue(ok(y));
  vi.spyOn(api.pdde, "entity").mockResolvedValue(ok(null));
  vi.spyOn(api.pdde, "carryovers").mockResolvedValue(ok([]));
  render(<PddeArea schoolId={SCHOOL_ID} />);
  return userEvent.setup();
}

const credit = (over: Record<string, unknown> = {}) =>
  line({ line_id: "l-credit", memo: "CREDITO FNDE PDDE BASICO CAPITAL", amount_cents: 360_000, ...over });
const programBasico = { program: "BASICO", program_label: null, received_cents: 360_000, yield_cents: 0, returned_cents: 0, spent_custeio_cents: 0, spent_capital_cents: 150_000, balance_cents: 210_000 };
const accounts = [{ id: "a1", nickname: "PDDE", bank_name: "Banco do Brasil", account_last4: null }];

describe("PddeArea", () => {
  it("sem conta do PDDE, diz onde cadastrar", async () => {
    setup(month([], { accounts: [] }));

    expect(await screen.findByText("Falta a conta do PDDE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Conciliação" })).toHaveAttribute("href", "/painel/conciliacao");
  });

  it("separa o que entrou do que foi gasto, com a contagem do que falta", async () => {
    const user = setup(month([credit(), line()]));

    expect(await screen.findByRole("tab", { name: /1 · Entrou\s?1/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /2 · Gastei\s?1/ })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Lançamentos da conta do PDDE" })).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("CREDITO FNDE PDDE BASICO CAPITAL")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /2 · Gastei/ }));
    expect(screen.getByText("PAGAMENTO MATERIAL ESCOLAR")).toBeInTheDocument();
    expect(screen.queryByText("CREDITO FNDE PDDE BASICO CAPITAL")).toBeNull();
  });

  it("uma entrada cujo texto diz programa e capital e confirmada com um clique", async () => {
    const classify = vi.spyOn(api.pdde, "classify").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(month([credit()]));

    expect(await screen.findByText("Sugestão: PDDE Básico · Capital")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(classify).toHaveBeenCalledTimes(1));
    expect(classify.mock.calls[0]![1]).toBe("l-credit");
    expect(classify.mock.calls[0]![2]).toEqual({ kind: "TRANSFER", program: "BASICO", economicCategory: "CAPITAL" });
  });

  it("uma entrada sem o programa no texto nao tem Confirmar: abre a escolha", async () => {
    setup(month([credit({ memo: "CREDITO DIVERSOS" })]));

    await screen.findByText("CREDITO DIVERSOS");
    expect(screen.queryByRole("button", { name: "Confirmar" })).toBeNull();
    expect(screen.getByRole("button", { name: "Escolher" })).toBeInTheDocument();
  });

  it("na compra, escolher o item define capital ou custeio, e a decisao vai para a API", async () => {
    const classify = vi.spyOn(api.pdde, "classify").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(month([line({ memo: "PIX VENTILADOR DE PAREDE" })]), year({ programs: [programBasico] }));
    await user.click(await screen.findByRole("tab", { name: /2 · Gastei/ }));
    await user.click(screen.getByRole("button", { name: "O que foi comprado?" }));
    const dialog = await screen.findByRole("dialog");

    // The text of the statement already suggests the item, and the item sets "Capital".
    expect(within(dialog).getByLabelText("Item")).toHaveValue("obj:Eletro ou eletrônico (ventilador, geladeira, TV)");
    expect(within(dialog).getByRole("radio", { name: "Capital" })).toBeChecked();
    // One program only: it is not asked.
    expect(within(dialog).queryByLabelText("Programa")).toBeNull();

    await user.selectOptions(within(dialog).getByLabelText("Item"), "obj:Serviço (mão de obra, frete, instalação)");
    expect(within(dialog).getByRole("radio", { name: "Custeio" })).toBeChecked();
    await user.click(within(dialog).getByRole("radio", { name: "Capital" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(classify).toHaveBeenCalledTimes(1));
    expect(classify.mock.calls[0]![2]).toMatchObject({ kind: "EXPENSE", program: "BASICO", economicCategory: "CAPITAL", object: "Serviço (mão de obra, frete, instalação)" });
  });

  it("sem item escolhido, a compra nao salva", async () => {
    const classify = vi.spyOn(api.pdde, "classify").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(month([line({ memo: "PAGAMENTO DIVERSOS" })]));
    await user.click(await screen.findByRole("tab", { name: /2 · Gastei/ }));
    await user.click(screen.getByRole("button", { name: "O que foi comprado?" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(within(dialog).getByRole("alert")).toHaveTextContent("Escolha o que foi comprado.");
    expect(classify).not.toHaveBeenCalled();
  });

  it("uma compra classificada recebe notas; uma nota errada e anulada", async () => {
    const add = vi.spyOn(api.pdde, "addDocument").mockResolvedValue({ ok: true, data: { ok: true } });
    const voided = vi.spyOn(api.pdde, "voidDocument").mockResolvedValue({ ok: true, data: { ok: true } });
    const classified = line({
      status: "PARTIAL",
      classification: { kind: "EXPENSE", program: "BASICO", program_label: null, economic_category: "CAPITAL", object: "Móveis (mesa, cadeira, armário)", note: null },
      documents: [{ id: "d1", doc_kind: "RECEIPT", access_key: null, doc_number: "12", issued_on: "2025-03-19", vendor: "Papelaria Exemplo", amount_cents: 100_000, stamped: false, voided: false }],
      documented_cents: 100_000,
    });
    const user = setup(month([classified]));
    await user.click(await screen.findByRole("tab", { name: /2 · Gastei/ }));

    expect(screen.getByText("Falta R$ 500,00")).toBeInTheDocument();
    expect(screen.getByText(/sem carimbo/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Anular a nota de Papelaria Exemplo" }));
    expect(voided).toHaveBeenCalledWith(SCHOOL_ID, "d1");

    await user.click(screen.getByRole("button", { name: "Anexar nota" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Tipo"), "RECEIPT");
    await user.type(within(dialog).getByLabelText("Fornecedor"), "Gráfica Exemplo");
    await user.type(within(dialog).getByLabelText("Data da nota"), "2025-03-21");
    await user.click(within(dialog).getByRole("button", { name: "Anexar" }));

    await waitFor(() => expect(add).toHaveBeenCalledTimes(1));
    expect(add.mock.calls[0]![2]).toMatchObject({ docKind: "RECEIPT", vendor: "Gráfica Exemplo", issuedOn: "2025-03-21", amountCents: 50_000, stamped: true });
  });

  it("uma recusa da API vira texto, sem o codigo", async () => {
    vi.spyOn(api.pdde, "classify").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "rule_violation" } });
    const user = setup(month([credit({ memo: "CREDITO DIVERSOS" })]), year({ programs: [programBasico] }));
    await user.click(await screen.findByRole("button", { name: "Escolher" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: "Custeio" }));

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Não foi possível salvar");
    expect(screen.queryByText(/rule_violation/)).toBeNull();
  });
});

describe("PddeArea: entregar", () => {
  it("mostra o que falta, os avisos curtos e um botao para cada formulario do FNDE", async () => {
    const user = setup(
      month([line()]),
      year({
        pending_count: 3,
        accounts,
        programs: [{ ...programBasico, yield_cents: 1234 }],
        alerts: [
          { code: "fee_on_pdde_account", count: 1, cents: 1200, program: null, economic_category: null, date: null },
          { code: "spent_over_received", count: 0, cents: 5000, program: "BASICO", economic_category: "CAPITAL", date: null },
          { code: "pending_lines", count: 3, cents: 0, program: null, economic_category: null, date: null },
        ],
      }),
    );
    await user.click(await screen.findByRole("tab", { name: /3 · Entregar/ }));

    expect(await screen.findByText("Faltam 3 lançamentos")).toBeInTheDocument();
    expect(screen.getByText(/1 tarifa bancária na conta do PDDE \(R\$ 12,00\)/)).toBeInTheDocument();
    expect(screen.getByText(/PDDE Básico: R\$ 50,00 a mais em capital/)).toBeInTheDocument();
    const demo = screen.getByRole("link", { name: "Demonstrativo (PDF)" });
    expect(demo).toHaveAttribute("href", expect.stringContaining("/pdde/forms/demonstrativo.pdf?year="));
    expect(demo).toHaveAttribute("href", expect.stringContaining("program=BASICO"));
    expect(screen.getByRole("link", { name: "Relação de bens (PDF)" })).toHaveAttribute("href", expect.stringContaining("/pdde/forms/bens.pdf?year="));
    expect(screen.getByRole("link", { name: "Conciliação bancária (PDF)" })).toHaveAttribute("href", expect.stringMatching(/\/pdde\/forms\/conciliacao\.pdf\?year=\d{4}&account_id=a1$/));
    expect(screen.getByRole("list", { name: "Saldo por programa" })).toHaveTextContent("Saldo R$ 2.100,00");
    expect(screen.getByText(/Dados da escola para os formulários \(faltam\)/)).toBeInTheDocument();
  });

  it("sem pendencia, diz que esta tudo pronto; a relacao de bens so existe com gasto de capital", async () => {
    const user = setup(month([line()]), year({ pending_count: 0, programs: [{ ...programBasico, spent_capital_cents: 0 }] }));
    await user.click(await screen.findByRole("tab", { name: /3 · Entregar/ }));

    expect(await screen.findByText("Tudo pronto para entregar")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Relação de bens (PDF)" })).toBeNull();
  });

  it("salva os dados da escola e manda o CNPJ como foi digitado (a API confere)", async () => {
    const save = vi.spyOn(api.pdde, "saveEntity").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(month([line()]), year());
    await user.click(await screen.findByRole("tab", { name: /3 · Entregar/ }));
    await user.click(await screen.findByText(/Dados da escola para os formulários/));

    await user.type(screen.getByLabelText("Nome (como no cartão do CNPJ)"), "APM Exemplo");
    await user.type(screen.getByLabelText("CNPJ"), "11.222.333/0001-81");
    await user.type(screen.getByLabelText("Endereço"), "Rua das Flores, 100");
    await user.type(screen.getByLabelText("Município"), "Jundiaí");
    await user.click(screen.getByRole("button", { name: "Salvar os dados" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0]![1]).toEqual({ legalName: "APM Exemplo", cnpj: "11.222.333/0001-81", address: "Rua das Flores, 100", city: "Jundiaí", state: "SP" });
    expect(await screen.findByText("Dados salvos.")).toBeInTheDocument();
  });

  it("digita o saldo do ano anterior por programa", async () => {
    const save = vi.spyOn(api.pdde, "saveCarryover").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(month([line()]), year());
    await user.click(await screen.findByRole("tab", { name: /3 · Entregar/ }));
    await user.click(await screen.findByText(/Saldo que veio de/));

    await user.type(screen.getByLabelText("Saldo de custeio"), "30000");
    await user.click(screen.getByRole("button", { name: "Salvar o saldo" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0]).toMatchObject([SCHOOL_ID, expect.any(Number), { program: "BASICO", custeioCents: 30_000, capitalCents: 0 }]);
  });
});
