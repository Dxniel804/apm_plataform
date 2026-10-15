import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseReconciliation } from "@/lib/api/reconciliation";
import type { BankAccount, Reconciliation, StatementImport } from "@/lib/api/types";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { ReconciliationArea } from "./ReconciliationArea";

const MANAGER = ["reconciliation:manage", "statement:read"];
const ACCOUNT: BankAccount = { id: "a1", nickname: "Conta principal", bankName: "Banco do Brasil", accountLast4: "4567", purpose: "GENERAL", isActive: true };
const IMPORT: StatementImport = { id: "i1", bankAccountId: "a1", periodStart: "2026-10-01", periodEnd: "2026-10-31", lineCount: 4, newLineCount: 3, closingBalanceCents: null, createdAt: "2026-10-14T20:00:00Z" };

const line = (id: string, amount: number, memo: string, extra: Record<string, unknown> = {}) => ({ line_id: id, posted_on: "2026-10-05", amount_cents: amount, memo, end_to_end_id: null, looks_like_fee: false, ...extra });
const entry = (id: string, code: number, amount: number, net: number | null = null) => ({ transaction_id: id, reference_code: code, kind: "CONTRIBUTION", day: "2026-10-05", amount_cents: amount, net_cents: net });
const REPORT: Reconciliation = parseReconciliation({
  statement: { id: "i1", bank_account_id: "a1", period_start: "2026-10-01", period_end: "2026-10-31", line_count: 4, new_line_count: 3, closing_balance_cents: null, created_at: "2026-10-14T20:00:00Z" },
  matched: [{ line: line("l1", 2920, "PIX RECEBIDO"), entry: entry("t1", 21, 3000, 2920) }],
  missing_in_system: [line("l2", -80, "TARIFA PIX", { looks_like_fee: true })],
  missing_in_bank: [entry("t3", 23, 4000)],
  divergences: [{ line: line("l4", 100, "PIX"), candidates: [entry("t4", 24, 2000)], reason: "amount_differs" }],
})!;

beforeEach(() => {
  vi.spyOn(api.reconciliation, "accounts").mockResolvedValue({ ok: true, data: [ACCOUNT] });
  vi.spyOn(api.reconciliation, "imports").mockResolvedValue({ ok: true, data: [IMPORT] });
});
afterEach(() => vi.restoreAllMocks());

describe("Conciliacao", () => {
  it("quem nao tem reconciliation:manage recebe um aviso e nenhuma chamada a API", () => {
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={["campaigns:manage"]} />);
    expect(screen.getByRole("note")).toHaveTextContent("não mexe na conciliação");
    expect(api.reconciliation.accounts).not.toHaveBeenCalled();
  });

  it("mostra as contas (so os ultimos digitos) e os extratos ja enviados", async () => {
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const accounts = await screen.findByRole("list", { name: "Contas bancárias" });
    expect(accounts).toHaveTextContent("Conta principal");
    expect(accounts).toHaveTextContent("final 4567");
    expect(screen.getByRole("list", { name: "Extratos enviados" })).toHaveTextContent("4 lançamentos (3 novos)");
  });

  it("abre a comparacao e mostra as quatro partes com a contagem de cada uma", async () => {
    vi.spyOn(api.reconciliation, "compare").mockResolvedValue({ ok: true, data: REPORT });
    const user = userEvent.setup();
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);

    await user.click(await screen.findByRole("button", { name: /Ver a comparação do extrato/ }));

    expect(await screen.findByRole("button", { name: "Conferidos (1)" })).toBeInTheDocument();
    expect(screen.getByText(/o banco recebe R\$\s?29,20/)).toBeInTheDocument(); // the fee already left
    await user.click(screen.getByRole("button", { name: "Faltam no sistema (1)" }));
    expect(screen.getByText(/TARIFA PIX/)).toBeInTheDocument();
    expect(screen.getByText("parece tarifa")).toBeInTheDocument();
    expect(screen.getByText("-R$ 0,80")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Faltam no extrato (1)" }));
    expect(screen.getByText(/Contribuição nº 23/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Divergências (1)" }));
    expect(screen.getByText(/o valor é outro/)).toBeInTheDocument();
    expect(screen.getByText(/não adivinha/)).toBeInTheDocument();
  });

  it("registra a tarifa que o banco cobrou depois de a pessoa confirmar", async () => {
    vi.spyOn(api.reconciliation, "compare").mockResolvedValue({ ok: true, data: REPORT });
    const act = vi.spyOn(api.reconciliation, "actOnLine").mockResolvedValue({ ok: true, data: { lineId: "l2", action: "REGISTERED", transactionId: "t9", referenceCode: "APM-000030" } });
    const user = userEvent.setup();
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    await user.click(await screen.findByRole("button", { name: /Ver a comparação do extrato/ }));
    await user.click(await screen.findByRole("button", { name: "Faltam no sistema (1)" }));

    await user.click(screen.getByRole("button", { name: /Registrar a tarifa de R\$\s?0,80/ }));
    expect(act).not.toHaveBeenCalled(); // so abre a confirmacao
    const dialog = await screen.findByRole("dialog", { name: "Registrar tarifa bancária" });
    await user.click(within(dialog).getByRole("button", { name: "Confirmar e registrar" }));

    await waitFor(() => expect(act).toHaveBeenCalledWith(SCHOOL_ID, "l2", { action: "REGISTER_FEE" }));
    expect(await screen.findByText(/Registrado no caixa \(APM-000030\)/)).toBeInTheDocument();
  });

  it("ignorar uma linha exige o motivo", async () => {
    vi.spyOn(api.reconciliation, "compare").mockResolvedValue({ ok: true, data: REPORT });
    const act = vi.spyOn(api.reconciliation, "actOnLine").mockResolvedValue({ ok: true, data: { lineId: "l2", action: "IGNORED", transactionId: null, referenceCode: null } });
    const user = userEvent.setup();
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    await user.click(await screen.findByRole("button", { name: /Ver a comparação do extrato/ }));
    await user.click(await screen.findByRole("button", { name: "Faltam no sistema (1)" }));

    await user.click(screen.getByRole("button", { name: /Ignorar a linha/ }));
    const dialog = await screen.findByRole("dialog", { name: "Ignorar esta linha" });
    await user.click(within(dialog).getByRole("button", { name: "Ignorar a linha" }));
    expect(within(dialog).getByText(/Explique o motivo/)).toBeInTheDocument();
    expect(act).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText(/Motivo/), "Pago pela prefeitura");
    await user.click(within(dialog).getByRole("button", { name: "Ignorar a linha" }));

    await waitFor(() => expect(act).toHaveBeenCalledWith(SCHOOL_ID, "l2", { action: "IGNORE", reason: "Pago pela prefeitura" }));
  });

  it("envia o arquivo OFX com a conta escolhida e avisa quantos lancamentos sao novos", async () => {
    const send = vi.spyOn(api.reconciliation, "import").mockResolvedValue({ ok: true, data: IMPORT });
    vi.spyOn(api.reconciliation, "compare").mockResolvedValue({ ok: true, data: REPORT });
    const user = userEvent.setup();
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);
    const file = new File(["<OFX></OFX>"], "extrato.ofx", { type: "application/x-ofx" });

    await user.upload(await screen.findByLabelText("Arquivo OFX do extrato"), file);

    await waitFor(() => expect(send).toHaveBeenCalledWith(SCHOOL_ID, "a1", file));
    expect(await screen.findByRole("status")).toHaveTextContent("3 lançamentos novos");
  });

  it("os erros do envio viram frases em portugues", async () => {
    vi.spyOn(api.reconciliation, "import").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "not_an_ofx_file" } });
    const user = userEvent.setup();
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);

    await user.upload(await screen.findByLabelText("Arquivo OFX do extrato"), new File(["x"], "extrato.ofx", { type: "application/x-ofx" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("não é um extrato OFX");
  });

  it("cadastra uma conta com os ultimos digitos e recarrega a lista", async () => {
    const create = vi.spyOn(api.reconciliation, "createAccount").mockResolvedValue({ ok: true, data: ACCOUNT });
    const user = userEvent.setup();
    render(<ReconciliationArea schoolId={SCHOOL_ID} permissions={MANAGER} />);

    await user.click(await screen.findByRole("button", { name: "Nova conta" }));
    const dialog = await screen.findByRole("dialog", { name: "Nova conta bancária" });
    await user.click(within(dialog).getByRole("button", { name: "Salvar conta" }));
    expect(within(dialog).getByText(/Dê um apelido/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Apelido"), "PDDE");
    await user.type(within(dialog).getByLabelText("Banco"), "Caixa");
    await user.type(within(dialog).getByLabelText(/Últimos dígitos/), "98765");
    await user.click(within(dialog).getByRole("button", { name: /PDDE/ }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar conta" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith(SCHOOL_ID, { nickname: "PDDE", bankName: "Caixa", accountLast4: "9876", purpose: "PDDE" }));
    await waitFor(() => expect(api.reconciliation.accounts).toHaveBeenCalledTimes(2));
  });
});

describe("datas do extrato", () => {
  it("um dia e um dia: 14 de outubro continua 14 de outubro (sem escorregar por causa do fuso)", async () => {
    const { formatDayLong } = await import("@/lib/format");
    expect(formatDayLong("2026-10-14")).toBe("14 de outubro de 2026");
    expect(formatDayLong("2026-01-01")).toBe("1 de janeiro de 2026");
    expect(formatDayLong("não é data")).toBe("não é data");
  });
});
