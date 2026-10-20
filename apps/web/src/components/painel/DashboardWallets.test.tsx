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
  it("abre no caixa da APM, diz isso no titulo e mostra ao lado o saldo do PDDE, sem somar", async () => {
    setup("apm");

    expect(screen.getByRole("heading", { name: "Caixa da APM" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "APM" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("PDDE: saldo")).toBeInTheDocument();
    expect(screen.getByText("PDDE: saldo").parentElement).toHaveTextContent("R$ 1.900,00");
    // The balance of the APM (the usual dashboard) is the APM's alone.
    expect(await screen.findByRole("heading", { name: /saldo em caixa em outubro de 2026/ })).toBeInTheDocument();
    expect(screen.getByText("R$ 684,10")).toBeInTheDocument();
  });

  it("clicar em PDDE pede a troca de carteira", async () => {
    const { user, onWalletChange } = setup("apm");

    await user.click(screen.getByRole("tab", { name: "PDDE" }));

    expect(onWalletChange).toHaveBeenCalledWith("pdde");
  });

  it("a carteira PDDE tem o titulo, o saldo, o que entrou e saiu, o saldo de cada programa e os lancamentos", async () => {
    setup("pdde", month([line(), line({ line_id: "l2", memo: "PAGAMENTO VENTILADOR", amount_cents: -150_000, status: "PENDING" })]));

    expect(screen.getByRole("heading", { name: "PDDE" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Saldo do PDDE" })).toHaveTextContent("R$ 1.900,00");
    expect(screen.getByText(/Entrou em outubro de 2026/).parentElement).toHaveTextContent("R$ 3.600,00");
    expect(screen.getByText(/Saiu em outubro de 2026/).parentElement).toHaveTextContent("R$ 1.500,00");
    expect(screen.getByRole("list", { name: "Saldo por programa" })).toHaveTextContent("PDDE Básico");
    const rows = within(screen.getByRole("region", { name: "Lançamentos do PDDE no mês" })).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("CREDITO FNDE PDDE BASICO CAPITAL");
    expect(rows[0]).toHaveTextContent("Classificar");
    expect(rows[1]).toHaveTextContent("PAGAMENTO VENTILADOR");
    // The other wallet is told by its balance and nothing is added to it.
    expect(await screen.findByText("Caixa da APM: saldo")).toBeInTheDocument();
    expect(screen.getByText("Caixa da APM: saldo").parentElement).toHaveTextContent("R$ 684,10");
  });

  it("mostra quantos lancamentos faltam e leva ao PDDE", async () => {
    setup("pdde");

    const pendings = await screen.findByRole("region", { name: "Pendências do PDDE" });
    expect(pendings).toHaveTextContent("2 lançamentos sem classificar ou sem nota");
    expect(within(pendings).getByRole("link", { name: "Abrir o PDDE" })).toHaveAttribute("href", "/painel/pdde");
  });

  it("sem conta do PDDE, diz onde cadastrar", async () => {
    setup("pdde", month([], []));

    expect(await screen.findByText("Falta a conta do PDDE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Conciliação" })).toHaveAttribute("href", "/painel/conciliacao");
  });

  it("trocar o mes na carteira PDDE avisa a tela", async () => {
    const { user, onPeriodChange } = setup("pdde");
    await screen.findByRole("region", { name: "Saldo do PDDE" });

    await user.selectOptions(screen.getByLabelText("Mês"), "2026-09");

    await waitFor(() => expect(onPeriodChange).toHaveBeenCalledWith("2026-09"));
  });

  it("o saldo principal e o do banco, com a data do extrato; o que a classificacao nao cobre e dito", async () => {
    setup("pdde", month([line()], undefined, bank(500_000)));

    const balance = await screen.findByRole("region", { name: "Saldo do PDDE" });
    expect(balance).toHaveTextContent("Saldo na conta em 15 de outubro de 2026");
    expect(balance).toHaveTextContent("R$ 5.000,00");
    // The classification leaves R$ 1.900,00: the other R$ 3.100,00 is money that came and was not classified yet.
    expect(balance).toHaveTextContent("R$ 3.100,00 do saldo ainda não está classificado.");
    // The other wallet's hint uses the bank balance too.
    expect(await screen.findByText("Caixa da APM: saldo")).toBeInTheDocument();
  });

  it("se a classificacao mostra mais que o banco, pede para conferir", async () => {
    setup("pdde", month([line()], undefined, bank(100_000)));

    const balance = await screen.findByRole("region", { name: "Saldo do PDDE" });
    expect(balance).toHaveTextContent("R$ 1.000,00");
    expect(balance).toHaveTextContent("A classificação mostra");
    expect(balance).toHaveTextContent("R$ 900,00");
    expect(balance).toHaveTextContent("a mais que o banco. Confira.");
  });

  it("sem extrato com saldo, mostra o classificado e pede o extrato", async () => {
    setup("pdde", month([line()], undefined, bank(null, null)));

    const balance = await screen.findByRole("region", { name: "Saldo do PDDE" });
    expect(balance).toHaveTextContent("Saldo pelo que foi classificado");
    expect(balance).toHaveTextContent("R$ 1.900,00");
    expect(balance).toHaveTextContent("Importe o extrato (PDF ou OFX) para ver o saldo do banco.");
  });

  it("o saldo do PDDE ao lado da APM tambem e o do banco", async () => {
    setup("apm", month([line()], undefined, bank(500_000)));

    expect((await screen.findByText("PDDE: saldo")).parentElement).toHaveTextContent("R$ 5.000,00");
  });
});
