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
  render(<PddeArea schoolId={SCHOOL_ID} />);
  return userEvent.setup();
}

describe("PddeArea", () => {
  it("sem conta do PDDE, explica onde cadastrar", async () => {
    setup(month([], { accounts: [] }));

    expect(await screen.findByText("Falta a conta do PDDE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Conciliação" })).toHaveAttribute("href", "/painel/conciliacao");
  });

  it("lista as linhas com a situacao, e os avisos e o saldo de cada programa", async () => {
    setup(
      month([line(), line({ line_id: "l-ok", memo: "CREDITO REPASSE", amount_cents: 1_000_000, status: "DONE", classification: { kind: "TRANSFER", program: "BASICO", program_label: null, economic_category: null, object: null, note: null } })]),
      year({
        programs: [{ program: "BASICO", program_label: null, received_cents: 1_000_000, spent_custeio_cents: 0, spent_capital_cents: 150_000, balance_cents: 850_000 }],
        alerts: [
          { code: "fee_on_pdde_account", count: 1, cents: 1200, program: null, economic_category: null, date: null },
          { code: "spent_over_received", count: 0, cents: 5000, program: "BASICO", economic_category: "CAPITAL", date: null },
        ],
      }),
    );

    const list = await screen.findByRole("list", { name: "Lançamentos da conta do PDDE" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("PAGAMENTO MATERIAL ESCOLAR");
    expect(rows[0]).toHaveTextContent("Pendente");
    expect(rows[1]).toHaveTextContent("Concluída");
    expect(await screen.findByText(/1 tarifa bancária na conta do PDDE \(R\$ 12,00\)/)).toBeInTheDocument();
    expect(screen.getByText(/gastou R\$ 50,00 a mais em capital/)).toBeInTheDocument();
    const balances = screen.getByRole("list", { name: "Saldo por programa" });
    expect(balances).toHaveTextContent("Saldo R$ 8.500,00");
  });

  it("classifica uma despesa: pede custeio ou capital e o objeto, e manda a decisao", async () => {
    const classify = vi.spyOn(api.pdde, "classify").mockResolvedValue({ ok: true, data: { ok: true } });
    const user = setup(month([line()]));
    await user.click(await screen.findByRole("button", { name: "Classificar" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Despesa precisa de custeio ou capital e do objeto.");
    expect(classify).not.toHaveBeenCalled();

    await user.selectOptions(within(dialog).getByLabelText("Custeio ou capital"), "CAPITAL");
    await user.type(within(dialog).getByLabelText("Objeto da despesa"), "Material permanente");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(classify).toHaveBeenCalledTimes(1));
    expect(classify.mock.calls[0]![1]).toBe("l-debit");
    expect(classify.mock.calls[0]![2]).toMatchObject({ kind: "EXPENSE", program: "BASICO", economicCategory: "CAPITAL", object: "Material permanente" });
  });

  it("uma despesa classificada recebe documentos; um documento errado e anulado", async () => {
    const add = vi.spyOn(api.pdde, "addDocument").mockResolvedValue({ ok: true, data: { ok: true } });
    const voided = vi.spyOn(api.pdde, "voidDocument").mockResolvedValue({ ok: true, data: { ok: true } });
    const classified = line({
      status: "PARTIAL",
      classification: { kind: "EXPENSE", program: "BASICO", program_label: null, economic_category: "CAPITAL", object: "Material permanente", note: null },
      documents: [{ id: "d1", doc_kind: "RECEIPT", access_key: null, doc_number: "12", issued_on: "2025-03-19", vendor: "Papelaria Exemplo", amount_cents: 100_000, stamped: false, voided: false }],
      documented_cents: 100_000,
    });
    const user = setup(month([classified]));

    expect(await screen.findByText(/Comprovado R\$ 1.000,00 de R\$ 1.500,00/)).toBeInTheDocument();
    expect(screen.getByText(/sem o carimbo do programa/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Anular o documento de Papelaria Exemplo" }));
    expect(voided).toHaveBeenCalledWith(SCHOOL_ID, "d1");

    await user.click(screen.getByRole("button", { name: "Registrar documento" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Tipo de documento"), "RECEIPT");
    await user.type(within(dialog).getByLabelText("Fornecedor"), "Gráfica Exemplo");
    await user.type(within(dialog).getByLabelText("Data do documento"), "2025-03-21");
    await user.click(within(dialog).getByRole("button", { name: "Registrar" }));

    await waitFor(() => expect(add).toHaveBeenCalledTimes(1));
    expect(add.mock.calls[0]![2]).toMatchObject({ docKind: "RECEIPT", vendor: "Gráfica Exemplo", issuedOn: "2025-03-21", amountCents: 50_000, stamped: false });
  });

  it("uma recusa da API vira texto, sem o codigo", async () => {
    vi.spyOn(api.pdde, "classify").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "rule_violation" } });
    const user = setup(month([line({ amount_cents: 1_000_000, memo: "CREDITO" })]));
    await user.click(await screen.findByRole("button", { name: "Classificar" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Não foi possível salvar");
    expect(screen.queryByText(/rule_violation/)).toBeNull();
  });
});
