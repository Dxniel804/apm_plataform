import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseMonth, parseYear, type PddeMonth, type PddeYear } from "@/lib/api/pdde";
import type { ApiResult } from "@/lib/api/types";
import { SCHOOL_ID, SUMMARY, page } from "@/test-utils/statement-fixtures";
import { DashboardWallets } from "./DashboardWallets";

const TREASURER = ["statement:read", "reports:read", "reconciliation:manage"];
const ok = <T,>(data: T): ApiResult<T> => ({ ok: true, data });

const programBasico = { program: "BASICO", program_label: null, received_cents: 360_000, yield_cents: 0, returned_cents: 0, spent_custeio_cents: 20_000, spent_capital_cents: 150_000, balance_cents: 190_000 };
const line = (over: Record<string, unknown> = {}) => ({
  line_id: "l1", account_id: "a1", account_nickname: "PDDE", posted_on: "2026-10-06", amount_cents: 360_000, memo: "CREDITO FNDE PDDE BASICO CAPITAL",
  looks_like_fee: false, classification: null, documents: [], documented_cents: 0, status: "PENDING", ...over,
});
const done = (kind: string) => ({ kind, program: "BASICO", program_label: null, economic_category: null, object: null, note: null, payment_number: null });
const month = (lines: unknown[], accounts = [{ id: "a1", nickname: "PDDE", bank_name: "Banco do Brasil", account_last4: null }], bank_balances: unknown[] = []) =>
  parseMonth({ period: "2026-10", accounts, bank_balances, lines, pending_count: lines.length, alerts: [] }) as PddeMonth;
const bank = (balance_cents: number | null, as_of: string | null = "2026-10-15") => [{ account_id: "a1", account_nickname: "PDDE", balance_cents, as_of }];
const year = (over: Record<string, unknown> = {}) =>
  parseYear({ year: 2026, accounts: [], programs: [programBasico], pending_count: 2, year_end: [], alerts: [], ...over }) as PddeYear;

afterEach(() => vi.restoreAllMocks());

function setup(wallet: "apm" | "pdde", m: PddeMonth = month([line()]), y: PddeYear = year()) {
  vi.spyOn(api.statement, "summary").mockResolvedValue(ok(SUMMARY));
  vi.spyOn(api.statement, "pending").mockResolvedValue(ok(page([])));
  vi.spyOn(api.statement, "series").mockResolvedValue({ ok: false, error: { kind: "problem", status: 500, code: "x" } });
  vi.spyOn(api.statement, "goal").mockResolvedValue({ ok: false, error: { kind: "problem", status: 500, code: "x" } });
  vi.spyOn(api.pdde, "month").mockResolvedValue(ok(m));
  vi.spyOn(api.pdde, "year").mockResolvedValue(ok(y));
  const onWalletChange = vi.fn();
  const onPeriodChange = vi.fn();
  render(<DashboardWallets schoolId={SCHOOL_ID} permissions={TREASURER} period="2026-10" wallet={wallet} onPeriodChange={onPeriodChange} onWalletChange={onWalletChange} />);
  return { user: userEvent.setup(), onWalletChange, onPeriodChange };
}

describe("DashboardWallets", () => {
  it("abre no caixa da APM, com as abas, o mes e os botoes na mesma linha, e nao mostra o saldo da outra carteira", async () => {
    setup("apm");

    expect(screen.getByRole("heading", { name: "Caixa da APM" })).toBeInTheDocument();
    const tab = screen.getByRole("tab", { name: "APM" });
    expect(tab).toHaveAttribute("aria-selected", "true");
    // One toolbar row: the tabs, the month and the buttons share the same parent.
    const month = await screen.findByLabelText("Mês");
    expect(tab.closest("div[role=tablist]")!.parentElement).toBe(month.closest("div.relative")!.parentElement);
    expect((await screen.findByRole("link", { name: /Baixar PDF/ })).parentElement).toBe(tab.closest("div[role=tablist]")!.parentElement);
    expect(screen.queryByText(/PDDE: saldo|Caixa da APM: saldo/)).not.toBeInTheDocument();
    // The balance of the APM (the usual dashboard) is the APM's alone.
    expect(await screen.findByRole("heading", { name: /^saldo em caixa$/i })).toBeInTheDocument();
    expect(screen.getByText("R$ 684,10")).toBeInTheDocument();
  });

  it("cada carteira busca so o que e dela: a APM nao pede o PDDE e o PDDE nao pede o caixa da APM", async () => {
    setup("apm");
    await screen.findByRole("heading", { name: /^saldo em caixa$/i });
    expect(api.statement.summary).toHaveBeenCalledTimes(1);
    expect(api.pdde.month).not.toHaveBeenCalled();
    expect(api.pdde.year).not.toHaveBeenCalled();
  });

  it("na carteira PDDE as abas e o mes tambem ficam na mesma linha e o caixa da APM nao e pedido", async () => {
    setup("pdde");
    const month = await screen.findByLabelText("Mês");
    expect(screen.getByRole("tab", { name: "PDDE" }).closest("div[role=tablist]")!.parentElement).toBe(month.parentElement!.parentElement);
    expect(api.statement.summary).not.toHaveBeenCalled();
  });

  it("clicar em PDDE pede a troca de carteira", async () => {
    const { user, onWalletChange } = setup("apm");

    await user.click(screen.getByRole("tab", { name: "PDDE" }));

    expect(onWalletChange).toHaveBeenCalledWith("pdde");
  });

  it("a carteira PDDE tem o titulo, tres numeros, a execucao dos programas e a situacao dos lancamentos", async () => {
    setup("pdde", month([line(), line({ line_id: "l2", memo: "PAGAMENTO VENTILADOR", amount_cents: -150_000, classification: done("EXPENSE"), status: "PENDING" }), line({ line_id: "l3", memo: "JA RESOLVIDO", amount_cents: -1_000, classification: done("RETURN_TO_FNDE"), status: "DONE" })]));

    expect(screen.getByRole("heading", { name: "PDDE" })).toBeInTheDocument();
    const numbers = await screen.findByRole("region", { name: "Números do PDDE" });
    expect(within(numbers).getByRole("heading", { name: "Saldo classificado" }).parentElement).toHaveTextContent("R$ 1.900,00");
    expect(within(numbers).getByRole("heading", { name: "Entrou" }).parentElement).toHaveTextContent("R$ 3.600,00");
    expect(within(numbers).getByRole("heading", { name: "Saiu" }).parentElement).toHaveTextContent("R$ 1.510,00");
    // The old "by program" cards and the list of every line are gone: two bars say it.
    expect(screen.queryByRole("list", { name: "Saldo por programa" })).not.toBeInTheDocument();
    expect(screen.queryByText("CREDITO FNDE PDDE BASICO CAPITAL")).not.toBeInTheDocument();
    const execution = screen.getByRole("region", { name: "Execução por programa" });
    expect(within(execution).getByRole("img", { name: /Custeio gasto 6%, Capital gasto 42%, Saldo 53%/ })).toBeInTheDocument();
    const lines = screen.getByRole("region", { name: "Lançamentos do mês" });
    expect(within(lines).getByRole("img", { name: /Prontos 33%, Falta nota 33%, Falta classificar 33%/ })).toBeInTheDocument();
    expect(lines).toHaveTextContent("1 lançamento");
    expect(within(lines).getByRole("link", { name: "Abrir o PDDE" })).toHaveAttribute("href", "/painel/pdde");
  });

  it("lancamentos de outros meses pendentes sao ditos em uma linha", async () => {
    setup("pdde", month([line()]), year({ pending_count: 4 }));

    const lines = await screen.findByRole("region", { name: "Lançamentos do mês" });
    expect(lines).toHaveTextContent("3 em outros meses do ano.");
  });

  it("mes sem lancamentos: diz isso em vez de uma barra vazia", async () => {
    setup("pdde", month([]), year({ pending_count: 0 }));

    const lines = await screen.findByRole("region", { name: "Lançamentos do mês" });
    expect(lines).toHaveTextContent("Nenhum lançamento em outubro de 2026.");
    expect(within(lines).queryByRole("img")).not.toBeInTheDocument();
  });

  it("sem conta do PDDE, diz onde cadastrar", async () => {
    setup("pdde", month([], []));

    expect(await screen.findByText("Falta a conta do PDDE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Conciliação" })).toHaveAttribute("href", "/painel/conciliacao");
  });

  it("trocar o mes na carteira PDDE avisa a tela", async () => {
    const { user, onPeriodChange } = setup("pdde");
    await screen.findByRole("region", { name: "Números do PDDE" });

    await user.selectOptions(screen.getByLabelText("Mês"), "2026-09");

    await waitFor(() => expect(onPeriodChange).toHaveBeenCalledWith("2026-09"));
  });

  it("o saldo principal e o do banco, com a data do extrato; o que a classificacao nao cobre e dito", async () => {
    setup("pdde", month([line()], undefined, bank(500_000)));

    const balance = await screen.findByRole("region", { name: "Números do PDDE" });
    expect(balance).toHaveTextContent("Saldo na conta");
    expect(balance).toHaveTextContent("Extrato de 15 out");
    expect(balance).toHaveTextContent("R$ 5.000,00");
    // The classification leaves R$ 1.900,00: the other R$ 3.100,00 is money that came and was not classified yet.
    expect(balance).toHaveTextContent("R$ 3.100,00 ainda sem classificar");
  });

  it("se a classificacao mostra mais que o banco, pede para conferir", async () => {
    setup("pdde", month([line()], undefined, bank(100_000)));

    const balance = await screen.findByRole("region", { name: "Números do PDDE" });
    expect(balance).toHaveTextContent("R$ 1.000,00");
    expect(balance).toHaveTextContent(/Classificação.*R\$\s900,00.*acima do banco/);
  });

  it("sem extrato com saldo, mostra o classificado e pede o extrato", async () => {
    setup("pdde", month([line()], undefined, bank(null, null)));

    const balance = await screen.findByRole("region", { name: "Números do PDDE" });
    expect(balance).toHaveTextContent("Saldo classificado");
    expect(balance).toHaveTextContent("R$ 1.900,00");
    expect(balance).toHaveTextContent("Sem extrato importado");
  });
});
