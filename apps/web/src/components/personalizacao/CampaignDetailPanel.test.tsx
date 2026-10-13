import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiResult, CampaignDetail } from "@/lib/api/types";
import { CAMPAIGN_ID, ITEM_A, ITEM_B, detail, item } from "@/test-utils/campaign-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { CampaignDetailPanel } from "./CampaignDetailPanel";

const ok = (d: CampaignDetail): ApiResult<CampaignDetail> => ({ ok: true, data: d });
const fail = (code: string, status: number, fields?: Array<{ field: string; code: string }>): ApiResult<CampaignDetail> => ({
  ok: false,
  error: { kind: "problem", status, code, fields },
});
const png = (name = "capa.png") => new File([new Uint8Array(500)], name, { type: "image/png" });

/** Abre a janela "Editar campanha" (o texto e as datas ficam numa janela, como os outros formularios). */
async function openTextEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Editar texto e datas" }));
  return screen.getByRole("dialog", { name: "Editar campanha" });
}

function setup(d: CampaignDetail = detail()) {
  vi.spyOn(api.campaigns, "get").mockResolvedValue(ok(d));
  const onChanged = vi.fn();
  render(<CampaignDetailPanel schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={onChanged} />);
  return { onChanged, user: userEvent.setup() };
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

describe("editor de uma campanha", () => {
  it("mostra o texto, os produtos com preco e limite, e a previa como a familia ve", async () => {
    setup(detail({ description: "Barracas e jogos", endsOn: "2026-06-30" }));

    const summary = (await screen.findByRole("heading", { name: "Texto e datas" })).closest("section")!;
    expect(summary).toHaveTextContent("Festa Junina");
    expect(summary).toHaveTextContent("Barracas e jogos");
    expect(summary).toHaveTextContent("até 30 de jun");
    const products = screen.getByRole("list", { name: "Produtos da campanha" });
    expect(within(products).getAllByRole("listitem")).toHaveLength(2);
    expect(products).toHaveTextContent("Cachorro-quente");
    expect(products).toHaveTextContent("R$ 8,00");
    expect(products).toHaveTextContent("até 5 por pedido");
    expect(products).toHaveTextContent("R$ 6,50");
    expect(products).toHaveTextContent("sem limite por pedido");
    const preview = screen.getByRole("group", { name: "Pré-visualização da página da campanha" });
    expect(preview).toHaveTextContent("Festa Junina");
    expect(preview).toHaveTextContent("R$ 8,00");
    expect(preview).toHaveTextContent("À venda até 30 de jun");
  });

  it("a previa mostra so os produtos que estao ligados", async () => {
    setup(detail({ items: [item(), item({ id: ITEM_B, name: "Pamonha", isActive: false })] }));
    const preview = await screen.findByRole("group", { name: "Pré-visualização da página da campanha" });
    expect(preview).toHaveTextContent("Cachorro-quente");
    expect(preview).not.toHaveTextContent("Pamonha");
  });

  it("rascunho: so oferece 'Pôr à venda' depois de confirmar; a API devolve a campanha a venda", async () => {
    const { onChanged, user } = setup();
    const activate = vi.spyOn(api.campaigns, "activate").mockResolvedValue(ok(detail({ status: "ACTIVE" })));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.click(screen.getByRole("button", { name: "Pôr à venda" }));
    const confirm = await screen.findByRole("dialog", { name: "Pôr à venda" });
    expect(activate).not.toHaveBeenCalled();
    await user.click(within(confirm).getByRole("button", { name: "Pôr à venda" }));

    await waitFor(() => expect(activate).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID));
    expect(await screen.findByRole("status")).toHaveTextContent("Campanha à venda.");
    expect(screen.queryByRole("button", { name: "Pôr à venda" })).not.toBeInTheDocument(); // ja esta a venda
    expect(onChanged).toHaveBeenCalledWith("Campanha à venda.");
  });

  it("sem produto ligado a API recusa e o texto explica", async () => {
    const { user } = setup(detail({ items: [] }));
    vi.spyOn(api.campaigns, "activate").mockResolvedValue(fail("campaign_needs_a_product", 409));
    vi.spyOn(api.campaigns, "get").mockResolvedValue(ok(detail({ items: [] })));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.click(screen.getByRole("button", { name: "Pôr à venda" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Pôr à venda" })).getByRole("button", { name: "Pôr à venda" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("pelo menos um produto");
  });

  it("encerrar e definitivo: pede confirmacao e depois a campanha vira so leitura", async () => {
    const { user } = setup(detail({ status: "ACTIVE" }));
    const end = vi.spyOn(api.campaigns, "end").mockResolvedValue(ok(detail({ status: "ENDED" })));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.click(screen.getByRole("button", { name: "Encerrar campanha" }));
    const confirm = await screen.findByRole("dialog", { name: "Encerrar campanha" });
    expect(confirm).toHaveTextContent("Encerrar é definitivo");
    await user.click(within(confirm).getByRole("button", { name: "Encerrar de vez" }));

    await waitFor(() => expect(end).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID));
    expect(await screen.findByRole("note")).toHaveTextContent("foi encerrada");
    expect(screen.queryByRole("button", { name: "Editar texto e datas" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Novo produto" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Editar o produto/ })).not.toBeInTheDocument();
  });

  it("salva o texto e as datas; `null` apaga o que foi esvaziado", async () => {
    const { user, onChanged } = setup(detail({ endsOn: "2026-06-30" }));
    const update = vi.spyOn(api.campaigns, "update").mockResolvedValue(ok(detail({ title: "Festa de São João" })));
    const editor = await openTextEditor(user);
    const title = within(editor).getByLabelText("Título");

    await user.clear(title);
    await user.type(title, "  Festa de São João ");
    await user.clear(within(editor).getByLabelText(/Termina em/));
    await user.clear(within(editor).getByLabelText(/Texto para as famílias/));
    await user.click(within(editor).getByRole("button", { name: "Salvar texto e datas" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, { title: "Festa de São João", description: null, startsOn: null, endsOn: null }));
    expect(onChanged).toHaveBeenCalledWith("Campanha salva.");
  });

  it("titulo vazio e datas trocadas sao avisados sem falar com a API", async () => {
    const { user } = setup(detail({ startsOn: "2026-06-01" }));
    const update = vi.spyOn(api.campaigns, "update");
    const editor = await openTextEditor(user);

    await user.clear(within(editor).getByLabelText("Título"));
    await user.clear(within(editor).getByLabelText(/Termina em/));
    await user.type(within(editor).getByLabelText(/Termina em/), "2026-05-01");
    await user.click(within(editor).getByRole("button", { name: "Salvar texto e datas" }));

    expect(screen.getByText("Escreva o título da campanha.")).toBeInTheDocument();
    expect(screen.getByText("A data de fim não pode ser antes da data de início.")).toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
  });

  it("409 (a campanha mudou por baixo): avisa e recarrega do servidor", async () => {
    const { user } = setup();
    const get = vi.spyOn(api.campaigns, "get").mockResolvedValue(ok(detail({ status: "ENDED" })));
    vi.spyOn(api.campaigns, "update").mockResolvedValue(fail("invalid_state", 409));
    const editor = await openTextEditor(user);

    await user.type(within(editor).getByLabelText("Título"), "!");
    await user.click(within(editor).getByRole("button", { name: "Salvar texto e datas" }));

    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("note")).toHaveTextContent("foi encerrada");
  });
});

describe("produtos", () => {
  it("adiciona um produto: o preco vai em centavos e o limite so quando existe", async () => {
    const { user } = setup();
    const add = vi.spyOn(api.campaigns, "addItem").mockResolvedValue(ok(detail()));
    await screen.findByRole("heading", { name: "Texto e datas" });
    await user.click(screen.getByRole("button", { name: "Novo produto" }));
    const form = screen.getByRole("form", { name: "Adicionar produto" });

    await user.type(within(form).getByLabelText("Nome do produto"), "  Camiseta ");
    await user.type(within(form).getByLabelText("Preço"), "4500");
    await user.type(within(form).getByLabelText(/Limite por pedido/), "3");
    await user.click(within(form).getByRole("button", { name: "Adicionar produto" }));

    await waitFor(() => expect(add).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, { name: "Camiseta", description: undefined, priceCents: 4500, maxPerOrder: 3 }));
    expect(await screen.findByRole("status")).toHaveTextContent("Produto adicionado.");
  });

  it("avisa nome vazio, preco fora de R$ 1,00 a R$ 10.000,00 e limite invalido, sem chamar a API", async () => {
    const { user } = setup();
    const add = vi.spyOn(api.campaigns, "addItem");
    await screen.findByRole("heading", { name: "Texto e datas" });
    await user.click(screen.getByRole("button", { name: "Novo produto" }));
    const form = screen.getByRole("form", { name: "Adicionar produto" });

    await user.click(within(form).getByRole("button", { name: "Adicionar produto" }));
    expect(within(form).getByText("Escreva o nome do produto.")).toBeInTheDocument();
    expect(within(form).getByText("O preço vai de R$ 1,00 a R$ 10.000,00.")).toBeInTheDocument();
    await user.type(within(form).getByLabelText("Preço"), "5");
    await user.type(within(form).getByLabelText(/Limite por pedido/), "0");
    await user.click(within(form).getByRole("button", { name: "Adicionar produto" }));
    expect(within(form).getByText("O preço vai de R$ 1,00 a R$ 10.000,00.")).toBeInTheDocument(); // R$ 0,05
    expect(within(form).getByText("O limite por pedido vai de 1 a 99.")).toBeInTheDocument();
    expect(add).not.toHaveBeenCalled();
  });

  it("edita um produto: o preco novo vale para os proximos pedidos (a tela avisa)", async () => {
    const { user } = setup();
    const updateItem = vi.spyOn(api.campaigns, "updateItem").mockResolvedValue(ok(detail()));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.click(screen.getByRole("button", { name: "Editar o produto Cachorro-quente" }));
    const form = screen.getByRole("form", { name: "Editar o produto Cachorro-quente" });
    expect(within(form).getByText(/Os que já foram feitos não mudam/)).toBeInTheDocument();
    const price = within(form).getByLabelText("Preço");
    expect(price).toHaveValue("8,00");
    await user.clear(price);
    await user.type(price, "950");
    await user.clear(within(form).getByLabelText(/Limite por pedido/));
    await user.click(within(form).getByRole("button", { name: "Salvar produto" }));

    await waitFor(() =>
      expect(updateItem).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, ITEM_A, { name: "Cachorro-quente", description: "Pão, salsicha e molho da casa.", priceCents: 950, maxPerOrder: null }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Produto salvo.");
  });

  it("tira um produto da venda e o traz de volta (nunca o apaga)", async () => {
    const { user } = setup();
    const updateItem = vi.spyOn(api.campaigns, "updateItem").mockResolvedValue(ok(detail({ items: [item({ isActive: false })] })));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.click(screen.getByRole("button", { name: "Tirar da venda o produto Cachorro-quente" }));

    await waitFor(() => expect(updateItem).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, ITEM_A, { isActive: false }));
    expect(await screen.findByRole("status")).toHaveTextContent("Produto tirado da venda.");
    expect(screen.queryByRole("button", { name: /Apagar|Excluir|Remover o produto/ })).not.toBeInTheDocument();
  });
});

describe("imagens", () => {
  it("envia a capa (reduzida no navegador) e mostra o aviso; remover chama a API", async () => {
    const { user } = setup(detail({ hasCover: true, coverVersion: 1 }));
    vi.spyOn(api.campaigns, "image").mockResolvedValue({ ok: true, data: { blob: new Blob(["x"], { type: "image/png" }), contentType: "image/png" } });
    const setImage = vi.spyOn(api.campaigns, "setImage").mockResolvedValue(ok(detail({ hasCover: true, coverVersion: 2 })));
    const clear = vi.spyOn(api.campaigns, "clearImage").mockResolvedValue(ok(detail()));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.upload(screen.getByLabelText("Arquivo da capa da campanha"), png());
    await waitFor(() => expect(setImage).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID, expect.objectContaining({ name: "capa.png" })));
    expect(await screen.findByRole("status")).toHaveTextContent("Capa salva.");

    await user.click(screen.getByRole("button", { name: "Remover capa da campanha" }));
    await waitFor(() => expect(clear).toHaveBeenCalledWith(SCHOOL_ID, CAMPAIGN_ID));
  });

  it("um arquivo que nao e imagem e recusado no navegador", async () => {
    setup();
    const user = userEvent.setup({ applyAccept: false }); // o seletor de arquivos do navegador ja filtra; aqui ele deixa passar
    const setImage = vi.spyOn(api.campaigns, "setImage");
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.upload(screen.getByLabelText("Arquivo da capa da campanha"), new File(["%PDF"], "nota.pdf", { type: "application/pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("PNG, JPEG ou WebP");
    expect(setImage).not.toHaveBeenCalled();
  });

  it("erro da API na imagem aparece junto aos botoes", async () => {
    const { user } = setup();
    vi.spyOn(api.campaigns, "setImage").mockResolvedValue(fail("validation_error", 422, [{ field: "file", code: "image_malformed" }]));
    await screen.findByRole("heading", { name: "Texto e datas" });

    await user.upload(screen.getByLabelText("Arquivo da capa da campanha"), png());

    expect(await screen.findByText("Esta imagem está corrompida ou não é PNG, JPEG ou WebP.")).toBeInTheDocument();
  });
});

describe("falhas de leitura", () => {
  it("campanha que nao existe mais: texto em portugues", async () => {
    vi.spyOn(api.campaigns, "get").mockResolvedValue(fail("not_found", 404));
    render(<CampaignDetailPanel schoolId={SCHOOL_ID} campaignId={CAMPAIGN_ID} onChanged={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Não encontramos esta campanha");
  });

  it("nao escreve nada no console nem em storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const spies = [vi.spyOn(console, "error"), vi.spyOn(console, "warn"), vi.spyOn(console, "log")];
    const { user } = setup();
    vi.spyOn(api.campaigns, "updateItem").mockResolvedValue({ ok: false, error: { kind: "network" } });
    await screen.findByRole("heading", { name: "Texto e datas" });
    await user.click(screen.getByRole("button", { name: "Tirar da venda o produto Cachorro-quente" }));
    await screen.findByRole("alert");
    expect(setItem).not.toHaveBeenCalled();
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});
