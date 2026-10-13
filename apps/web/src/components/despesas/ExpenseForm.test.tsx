import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiResult, Attachment, ExpenseDetail, OcrSuggestion } from "@/lib/api/types";
import { CATEGORY, detail } from "@/test-utils/expense-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { ExpenseForm, dayInSchoolZone } from "./ExpenseForm";

const CATEGORIES = [CATEGORY, { id: "c2", key: "services", name: "Serviços" }];
const ok = (d: ExpenseDetail): ApiResult<ExpenseDetail> => ({ ok: true, data: d });
const att: Attachment = { id: "a", kind: "INVOICE", fileName: "nota.pdf", contentType: "application/pdf", sizeBytes: 9, uploadedByUserId: "u", createdAt: "2026-10-06T10:00:00Z" };

function setup(props: Partial<React.ComponentProps<typeof ExpenseForm>> = {}) {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  render(<ExpenseForm schoolId={SCHOOL_ID} categories={CATEGORIES} onSaved={onSaved} onCancel={onCancel} {...props} />);
  return { onSaved, onCancel, user: userEvent.setup() };
}

async function fillBasics(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Valor"), "1500");
  await user.type(screen.getByLabelText("Descrição"), "Cola e papel");
}

afterEach(() => vi.restoreAllMocks());

describe("ExpenseForm", () => {
  it("nunca pede o nome de quem envia (vem da sessao) e comeca na primeira categoria e na data de hoje", () => {
    setup();
    expect(screen.queryByLabelText(/nome/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Categoria")).toHaveValue(CATEGORY.id);
    expect(screen.getByLabelText("Data da despesa")).toHaveValue(dayInSchoolZone());
    expect(screen.getByText(/não pedimos o seu nome/)).toBeInTheDocument();
  });

  it("salva rascunho: cria na escola, sem enviar, com paid_by escolhido e sem campos vazios", async () => {
    const create = vi.spyOn(api.expenses, "create").mockResolvedValue(ok(detail({ id: "novo", status: "DRAFT" })));
    const submit = vi.spyOn(api.expenses, "submit");
    const { user, onSaved } = setup();
    await fillBasics(user);
    await user.click(screen.getByLabelText("Foi paga pela APM"));
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    expect(create).toHaveBeenCalledWith(SCHOOL_ID, {
      amountCents: 1500, occurredAt: dayInSchoolZone(), categoryId: CATEGORY.id, description: "Cola e papel",
      vendor: undefined, purchaseReason: undefined, paymentMethod: undefined, paidBy: "APM",
    });
    expect(submit).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledWith("novo", "Rascunho salvo.");
  });

  it("salvar e enviar: cria, anexa o arquivo (INVOICE) e envia, nessa ordem", async () => {
    const order: string[] = [];
    vi.spyOn(api.expenses, "create").mockImplementation(async () => (order.push("create"), ok(detail({ id: "novo", status: "DRAFT" }))));
    const upload = vi.spyOn(api.expenses, "upload").mockImplementation(async () => (order.push("upload"), { ok: true, data: att }));
    const submit = vi.spyOn(api.expenses, "submit").mockImplementation(async () => (order.push("submit"), ok(detail({ status: "SUBMITTED" }))));
    const { user, onSaved } = setup();
    await fillBasics(user);
    await user.type(screen.getByLabelText("Motivo da compra"), "Aula de artes");
    await user.selectOptions(screen.getByLabelText("Forma de pagamento"), "PIX");
    await user.upload(screen.getByLabelText(/Nota ou recibo/), new File(["%PDF-1.4"], "nota.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Salvar e enviar para análise" }));
    expect(order).toEqual(["create", "upload", "submit"]);
    expect(upload).toHaveBeenCalledWith(SCHOOL_ID, "novo", expect.any(File), "INVOICE");
    expect(submit).toHaveBeenCalledWith(SCHOOL_ID, "novo");
    expect(onSaved).toHaveBeenCalledWith("novo", "Despesa enviada para a análise da gestão.");
  });

  it("para enviar exige anexo, motivo e forma de pagamento: avisa e nao chama a API", async () => {
    const create = vi.spyOn(api.expenses, "create");
    const { user } = setup();
    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Salvar e enviar para análise" }));
    expect(screen.getByText(/Informe o motivo da compra/)).toBeInTheDocument();
    expect(screen.getByText("Informe a forma de pagamento.")).toBeInTheDocument();
    expect(screen.getByText("Anexe a nota ou o recibo para enviar.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("valor, descricao e categoria: valida no cliente", async () => {
    const create = vi.spyOn(api.expenses, "create");
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    expect(screen.getByText("Informe o valor.")).toBeInTheDocument();
    expect(screen.getByText("Descreva a despesa.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("422 da API: erro ao lado do campo, em portugues (categoria indisponivel)", async () => {
    vi.spyOn(api.expenses, "create").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "validation_error", fields: [{ field: "category_id", code: "not_available" }] } });
    const { user, onSaved } = setup();
    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    expect(await screen.findByText("Escolha uma categoria da lista.")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("falha no upload: o rascunho fica salvo e a tela avisa (nao perde o que foi digitado)", async () => {
    vi.spyOn(api.expenses, "create").mockResolvedValue(ok(detail({ id: "novo", status: "DRAFT" })));
    vi.spyOn(api.expenses, "upload").mockResolvedValue({ ok: false, error: { kind: "problem", status: 415, code: "attachment_type_not_allowed" } });
    const submit = vi.spyOn(api.expenses, "submit");
    const { user, onSaved } = setup();
    await fillBasics(user);
    await user.upload(screen.getByLabelText(/Nota ou recibo/), new File(["x"], "nota.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    expect(submit).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledWith("novo", expect.stringContaining("Rascunho salvo, mas o arquivo não foi enviado."));
    expect(onSaved.mock.calls[0]![1]).toContain("PNG, JPEG, WebP ou PDF");
  });

  it("arquivo maior que 10 MB e recusado no cliente", async () => {
    const create = vi.spyOn(api.expenses, "create");
    const { user } = setup();
    await fillBasics(user);
    const big = new File(["x"], "grande.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    await user.upload(screen.getByLabelText(/Nota ou recibo/), big);
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    expect(screen.getByRole("alert")).toHaveTextContent("limite é de 10 MB");
    expect(create).not.toHaveBeenCalled();
  });

  it("editar: preenche com a despesa, usa PATCH e nao oferece 'quem pagou'", async () => {
    const update = vi.spyOn(api.expenses, "update").mockResolvedValue(ok(detail()));
    const { user, onSaved } = setup({ expense: detail({ status: "CORRECTION_REQUESTED", description: "Antiga", amountCents: 20000 }) });
    expect(screen.getByLabelText("Descrição")).toHaveValue("Antiga");
    expect(screen.queryByText("Quem pagou")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("Descrição"));
    await user.type(screen.getByLabelText("Descrição"), "Nova descrição");
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    expect(update).toHaveBeenCalledWith(SCHOOL_ID, detail().id, expect.objectContaining({ description: "Nova descrição", amountCents: 20000 }));
    expect(onSaved).toHaveBeenCalled();
  });

  it("nao escreve nada no console nem em storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const spies = [vi.spyOn(console, "error"), vi.spyOn(console, "warn"), vi.spyOn(console, "log")];
    vi.spyOn(api.expenses, "create").mockResolvedValue({ ok: false, error: { kind: "network" } });
    const { user } = setup();
    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    await screen.findByRole("alert");
    expect(setItem).not.toHaveBeenCalled();
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});

const photo = (name = "nota.png") => new File([new Uint8Array(500)], name, { type: "image/png" });
const suggestion = (patch: Partial<OcrSuggestion> = {}): OcrSuggestion => ({
  amountCents: 8750,
  occurredOn: "2026-09-10",
  vendor: "PAPELARIA CENTRAL LTDA",
  documentNumber: "11222333000181",
  confidence: { amount: 0.95, date: 0.9, vendor: 0.8, document: 0.9 },
  model: "demo",
  elapsedMs: 120,
  ...patch,
});
const read = (s: OcrSuggestion): ApiResult<OcrSuggestion> => ({ ok: true, data: s });
const SUGGESTED = "Sugerido pela leitura da nota. Confira.";

describe("ExpenseForm: ler a nota (OCR)", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
  });

  async function openReader(props: Partial<React.ComponentProps<typeof ExpenseForm>> = {}) {
    const view = setup({ ocrEnabled: true, ...props });
    await view.user.click(screen.getByRole("button", { name: "Ler a nota (OCR)" }));
    return view;
  }

  async function choosePhoto(user: ReturnType<typeof userEvent.setup>, file = photo()) {
    await user.upload(screen.getByLabelText("Escolher fotos da galeria"), file);
    await screen.findByRole("list", { name: "Fotos escolhidas" });
  }

  it("sem OCR no servidor (ou editando) so existe o preenchimento manual", () => {
    const { unmount } = render(<ExpenseForm schoolId={SCHOOL_ID} categories={CATEGORIES} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Ler a nota (OCR)" })).not.toBeInTheDocument();
    unmount();
    setup({ ocrEnabled: true, expense: detail({ status: "CORRECTION_REQUESTED" }) });
    expect(screen.queryByRole("group", { name: "Como preencher a despesa" })).not.toBeInTheDocument();
  });

  it("com OCR ligado oferece as duas entradas e comeca no manual", () => {
    setup({ ocrEnabled: true });
    expect(screen.getByRole("button", { name: "Preencher manualmente" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Ler a nota (OCR)" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText(/Nota ou recibo/)).toBeInTheDocument();
  });

  it("no modo OCR troca o anexo comum pela foto da nota e so le depois que ha foto", async () => {
    const { user } = await openReader();
    expect(screen.queryByLabelText(/Nota ou recibo/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ler a nota" })).toBeDisabled();
    await choosePhoto(user);
    expect(screen.getByRole("button", { name: "Ler a nota" })).toBeEnabled();
  });

  it("le a foto (uma so) e preenche valor, data, fornecedor e descricao, marcados como sugestao", async () => {
    const readReceipt = vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion()));
    const { user } = await openReader();
    const file = photo("cupom.png");
    await choosePhoto(user, file);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));

    await waitFor(() => expect(screen.getByLabelText("Valor")).toHaveValue("87,50"));
    expect(readReceipt).toHaveBeenCalledWith(SCHOOL_ID, expect.objectContaining({ name: "cupom.png" }));
    expect(screen.getByLabelText("Data da despesa")).toHaveValue("2026-09-10");
    expect(screen.getByLabelText("Fornecedor (opcional)")).toHaveValue("PAPELARIA CENTRAL LTDA");
    expect(screen.getByLabelText("Descrição")).toHaveValue("Compra em PAPELARIA CENTRAL LTDA");
    expect(screen.getAllByText(SUGGESTED)).toHaveLength(4);
    expect(screen.getByText("Leitura concluída. Confira os campos preenchidos antes de salvar.")).toBeInTheDocument();
    // Uma foto so: nao ha como escolher outra sem remover esta.
    expect(screen.getByRole("button", { name: "Escolher da galeria" })).toBeDisabled();
  });

  it("mexer num campo sugerido tira a marca so dele", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion()));
    const { user } = await openReader();
    await choosePhoto(user);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));
    await waitFor(() => expect(screen.getByLabelText("Valor")).toHaveValue("87,50"));

    await user.type(screen.getByLabelText("Valor"), "0");
    expect(screen.getAllByText(SUGGESTED)).toHaveLength(3);
    await user.type(screen.getByLabelText("Descrição"), "!");
    expect(screen.getAllByText(SUGGESTED)).toHaveLength(2);
  });

  it("campo lido com pouca certeza avisa para conferir com atencao", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion({ confidence: { amount: 0.4, date: 0.9, vendor: 0.9, document: 0.9 } })));
    const { user } = await openReader();
    await choosePhoto(user);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));

    expect(await screen.findByText("Leitura incerta: confira com atenção.")).toBeInTheDocument();
    expect(screen.getAllByText("Leitura incerta: confira com atenção.")).toHaveLength(1);
    expect(screen.getByText(/pouca certeza em alguns campos/)).toBeInTheDocument();
  });

  it("nao apaga o que a pessoa ja escreveu na descricao e ignora data no futuro", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion({ occurredOn: "2999-01-01" })));
    const { user } = await openReader();
    await user.type(screen.getByLabelText("Descrição"), "Material de artes");
    await choosePhoto(user);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));

    await waitFor(() => expect(screen.getByLabelText("Valor")).toHaveValue("87,50"));
    expect(screen.getByLabelText("Descrição")).toHaveValue("Material de artes");
    expect(screen.getByLabelText("Data da despesa")).toHaveValue(dayInSchoolZone());
  });

  it("leitura sem nenhum dado util avisa e deixa tudo como estava", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion({ amountCents: null, occurredOn: null, vendor: null, documentNumber: null })));
    const { user } = await openReader();
    await choosePhoto(user);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));

    expect(await screen.findByText(/Não consegui ler dados desta nota/)).toBeInTheDocument();
    expect(screen.getByLabelText("Valor")).toHaveValue("");
    expect(screen.queryByText(SUGGESTED)).not.toBeInTheDocument();
  });

  it("OCR fora do ar: explica em portugues e o cadastro segue com a foto anexada", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue({ ok: false, error: { kind: "problem", status: 503, code: "ocr_unavailable" } });
    const create = vi.spyOn(api.expenses, "create").mockResolvedValue(ok(detail({ id: "novo", status: "DRAFT" })));
    const upload = vi.spyOn(api.expenses, "upload").mockResolvedValue({ ok: true, data: att });
    const { user, onSaved } = await openReader();
    await choosePhoto(user, photo("manual.png"));
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));
    expect(await screen.findByText(/leitura automática da nota não está disponível/)).toBeInTheDocument();

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("novo", "Arquivo anexado."));
    expect(create).toHaveBeenCalledTimes(1);
    expect(upload).toHaveBeenCalledWith(SCHOOL_ID, "novo", expect.objectContaining({ name: "manual.png" }), "INVOICE");
  });

  it("salvar e enviar depois da leitura: cria com os campos lidos, anexa a MESMA foto (INVOICE) e envia", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion()));
    const order: string[] = [];
    const create = vi.spyOn(api.expenses, "create").mockImplementation(async () => (order.push("create"), ok(detail({ id: "novo", status: "DRAFT" }))));
    const upload = vi.spyOn(api.expenses, "upload").mockImplementation(async () => (order.push("upload"), { ok: true, data: att }));
    vi.spyOn(api.expenses, "submit").mockImplementation(async () => (order.push("submit"), ok(detail({ status: "SUBMITTED" }))));
    const { user, onSaved } = await openReader();
    await choosePhoto(user, photo("cupom.png"));
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));
    await waitFor(() => expect(screen.getByLabelText("Valor")).toHaveValue("87,50"));
    await user.type(screen.getByLabelText("Motivo da compra"), "Aula de artes");
    await user.selectOptions(screen.getByLabelText("Forma de pagamento"), "PIX");
    await user.click(screen.getByRole("button", { name: "Salvar e enviar para análise" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("novo", "Despesa enviada para a análise da gestão."));
    expect(order).toEqual(["create", "upload", "submit"]);
    expect(create).toHaveBeenCalledWith(SCHOOL_ID, expect.objectContaining({ amountCents: 8750, occurredAt: "2026-09-10", vendor: "PAPELARIA CENTRAL LTDA", description: "Compra em PAPELARIA CENTRAL LTDA" }));
    expect(upload).toHaveBeenCalledWith(SCHOOL_ID, "novo", expect.objectContaining({ name: "cupom.png" }), "INVOICE");
  });

  it("trocar para o manual descarta a foto, mas mantem o que foi preenchido", async () => {
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion()));
    const upload = vi.spyOn(api.expenses, "upload");
    vi.spyOn(api.expenses, "create").mockResolvedValue(ok(detail({ id: "novo", status: "DRAFT" })));
    const { user, onSaved } = await openReader();
    await choosePhoto(user);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));
    await waitFor(() => expect(screen.getByLabelText("Valor")).toHaveValue("87,50"));

    await user.click(screen.getByRole("button", { name: "Preencher manualmente" }));
    expect(screen.getByLabelText("Valor")).toHaveValue("87,50");
    expect(screen.getByLabelText(/Nota ou recibo/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Salvar rascunho" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("novo", "Rascunho salvo."));
    expect(upload).not.toHaveBeenCalled();
  });

  it("nao escreve nada no console nem em storage ao ler a nota", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const spies = [vi.spyOn(console, "error"), vi.spyOn(console, "warn"), vi.spyOn(console, "log")];
    vi.spyOn(api.expenses, "readReceipt").mockResolvedValue(read(suggestion()));
    const { user } = await openReader();
    await choosePhoto(user);
    await user.click(screen.getByRole("button", { name: "Ler a nota" }));
    await waitFor(() => expect(screen.getByLabelText("Valor")).toHaveValue("87,50"));
    expect(setItem).not.toHaveBeenCalled();
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});
