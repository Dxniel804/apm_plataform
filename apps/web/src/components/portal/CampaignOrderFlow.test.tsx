import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiError, ApiResult, CreatedContribution } from "@/lib/api/types";
import { CAMPAIGN_ID, ITEM_A, ITEM_B, publicCampaign, publicItem } from "@/test-utils/campaign-fixtures";
import { SCHOOL, TOKEN, state } from "@/test-utils/public-fixtures";
import { CampaignOrderFlow } from "./CampaignOrderFlow";

const created = (amountCents = 2250): CreatedContribution => ({ ...state({ amountCents }), token: TOKEN });
const okCreated = (amountCents?: number): ApiResult<CreatedContribution> => ({ ok: true, data: created(amountCents) });
const fail = (error: ApiError): ApiResult<CreatedContribution> => ({ ok: false, error });
const problem = (code: string, status: number, extra: Partial<ApiError> = {}) => fail({ kind: "problem", status, code, ...extra });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

beforeEach(() => {
  vi.spyOn(api.public, "contribution").mockResolvedValue({ ok: true, data: state() });
});
afterEach(() => vi.restoreAllMocks());

const add = async (user: ReturnType<typeof userEvent.setup>, name: string, times = 1) => {
  for (let i = 0; i < times; i += 1) await user.click(screen.getByRole("button", { name: `Adicionar um ${name}` }));
};

async function toReview(user: ReturnType<typeof userEvent.setup>) {
  await add(user, "Cachorro-quente", 2);
  await add(user, "Pamonha");
  await user.click(screen.getByRole("button", { name: "Continuar" }));
  await user.click(screen.getByRole("button", { name: "Continuar" })); // dados opcionais em branco
  expect(await screen.findByRole("heading", { name: "Confira antes de pagar" })).toBeInTheDocument();
}

const submit = () => screen.getByRole("button", { name: /Gerar Pix de/ });

describe("aluno e turma", () => {
  it("campanha que pede aluno e turma: a etapa de dados aparece e os dois campos sao obrigatorios", async () => {
    const create = vi.spyOn(api.public, "createOrder");
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign({ askStudentClass: true })} />);
    const user = userEvent.setup();
    await add(user, "Cachorro-quente");
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    expect(await screen.findByLabelText(/Nome do aluno/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Turma/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    expect(screen.getAllByText(/Informe|obrigat/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Confira antes de pagar" })).not.toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("com os dois preenchidos, o pedido segue e leva aluno e turma para a API", async () => {
    const create = vi.spyOn(api.public, "createOrder").mockResolvedValue(okCreated());
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign({ askStudentClass: true })} />);
    const user = userEvent.setup();
    await add(user, "Cachorro-quente");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.type(await screen.findByLabelText(/Nome do aluno/), "Ana Souza");
    await user.selectOptions(screen.getByLabelText(/Ano do aluno/), "3º ano");
    await user.selectOptions(screen.getByLabelText(/^Turma/), "A");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(await screen.findByRole("button", { name: /Gerar Pix de/ }));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0]![2]).toMatchObject({ identification: { studentName: "Ana Souza", classroom: "3º ano A" } });
  });

  it("campanha que nao pede: o aluno e a turma ficam escondidos quando a escola tambem nao pede", async () => {
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign({ askStudentClass: false })} />);
    const user = userEvent.setup();
    await add(user, "Cachorro-quente");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByLabelText(/Nome do responsável/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Nome do aluno/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Turma/)).not.toBeInTheDocument();
  });
});

describe("o carrinho", () => {
  it("mostra a campanha, os produtos com o preco e o limite, e o total sobe e desce com as quantidades", async () => {
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();

    expect(screen.getByRole("heading", { level: 1, name: /Festa Junina/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Escolha os produtos" })).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === "Etapa 1 de 4: Produtos")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Produtos da campanha" });
    expect(list).toHaveTextContent("Cachorro-quente");
    expect(list).toHaveTextContent("R$ 8,00");
    expect(list).toHaveTextContent("No máximo 5 por pedido.");
    expect(list).toHaveTextContent("R$ 6,50");
    expect(screen.getByText("Nenhum produto")).toBeInTheDocument();

    await add(user, "Cachorro-quente", 2);
    await add(user, "Pamonha");
    expect(screen.getAllByText("R$ 22,50").length).toBeGreaterThan(0); // 2 x 8,00 + 6,50
    expect(screen.getByText("3 itens")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tirar um Cachorro-quente" }));
    expect(screen.getAllByText("R$ 14,50").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Tirar um Pamonha" }));
    await user.click(screen.getByRole("button", { name: "Tirar um Cachorro-quente" }));
    expect(screen.getByRole("button", { name: "Tirar um Cachorro-quente" })).toBeDisabled(); // nao fica negativo
    expect(screen.getByText("Nenhum produto")).toBeInTheDocument();
  });

  it("o limite por pedido trava o + no valor do produto", async () => {
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();

    await add(user, "Cachorro-quente", 5);

    expect(within(screen.getByRole("group", { name: "Quantidade de Cachorro-quente" })).getByText("5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adicionar um Cachorro-quente" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Adicionar um Pamonha" })).toBeEnabled(); // sem limite
  });

  it("sem produto nenhum nao avanca: avisa na hora", async () => {
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Continuar" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Escolha pelo menos um produto.");
    expect(screen.getByRole("heading", { name: "Escolha os produtos" })).toBeInTheDocument();
  });

  it("Voltar leva de volta para a pagina da escola", () => {
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    expect(screen.getByRole("link", { name: "Voltar" })).toHaveAttribute("href", "/escola/demo-aurora");
  });
});

describe("o pedido", () => {
  it("revisao mostra uma linha por produto e o total; o POST leva QUAIS produtos e QUANTOS, nunca um preco", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const create = vi.spyOn(api.public, "createOrder").mockResolvedValue(okCreated());
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    await toReview(user);

    const review = screen.getByRole("list", { name: "Resumo da contribuição" });
    expect(review).toHaveTextContent("2 × R$ 8,00");
    expect(review).toHaveTextContent("1 × R$ 6,50");
    expect(review).toHaveTextContent("Total");
    expect(review).toHaveTextContent("R$ 22,50");
    expect(submit()).toHaveTextContent("Gerar Pix de R$ 22,50");

    await user.click(submit());

    expect(create).toHaveBeenCalledTimes(1);
    const [slug, campaignId, input, key] = create.mock.calls[0]!;
    expect(slug).toBe("demo-aurora");
    expect(campaignId).toBe(CAMPAIGN_ID);
    expect(input).toEqual({ lines: [{ itemId: ITEM_A, quantity: 2 }, { itemId: ITEM_B, quantity: 1 }], identification: {} });
    expect(JSON.stringify(input)).not.toMatch(/price|total|amount/i); // nunca um preco nem um total
    expect(key).toMatch(UUID);
    expect(await screen.findByRole("heading", { name: "Pague com Pix" })).toBeInTheDocument();
    expect(setItem).not.toHaveBeenCalled();
    expect(window.location.href).not.toContain(key);
  });

  it("se o servidor cobra outro valor (o preco mudou), a tela diz e mostra o valor da API", async () => {
    vi.spyOn(api.public, "createOrder").mockResolvedValue(okCreated(2450));
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    await toReview(user);
    await user.click(submit());

    expect(await screen.findByText(/Os preços mudaram desde que você abriu a página. O valor deste Pix é R\$ 24,50/)).toBeInTheDocument();
  });

  it("falha de rede e nova tentativa com o MESMO carrinho: reaproveita a mesma chave; mudar o carrinho troca a chave", async () => {
    const create = vi.spyOn(api.public, "createOrder").mockResolvedValueOnce(fail({ kind: "network" })).mockResolvedValueOnce(fail({ kind: "network" })).mockResolvedValueOnce(okCreated());
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    await toReview(user);
    await user.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível falar com o servidor");
    await user.click(submit());
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    expect(create.mock.calls[1]![3]).toBe(create.mock.calls[0]![3]);

    await user.click(screen.getByRole("button", { name: "Alterar os produtos" }));
    await add(user, "Pamonha");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(submit());
    await screen.findByRole("heading", { name: "Pague com Pix" });
    expect(create.mock.calls[2]![3]).not.toBe(create.mock.calls[0]![3]);
    expect(create.mock.calls[2]![2].lines).toEqual([{ itemId: ITEM_A, quantity: 2 }, { itemId: ITEM_B, quantity: 2 }]);
  });

  it("o servidor recusa um produto: volta para os produtos com o aviso na linha certa", async () => {
    vi.spyOn(api.public, "createOrder").mockResolvedValue(
      problem("validation_error", 422, { fields: [{ field: "lines[1].item_id", code: "unavailable" }, { field: "lines[0].quantity", code: "over_limit" }] }),
    );
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    await toReview(user);
    await user.click(submit());

    expect(await screen.findByRole("heading", { name: "Escolha os produtos" })).toBeInTheDocument();
    expect(screen.getByText("Alguns produtos não estão mais como você escolheu. Confira os avisos abaixo.")).toBeInTheDocument();
    const [hotDog, pamonha] = screen.getAllByRole("listitem").filter((li) => li.textContent?.match(/Cachorro-quente|Pamonha/));
    expect(hotDog).toHaveTextContent("Passa do limite por pedido deste produto.");
    expect(pamonha).toHaveTextContent("Este produto não está mais à venda.");
    // mexer no produto tira o aviso dele
    await user.click(within(pamonha!).getByRole("button", { name: "Tirar um Pamonha" }));
    expect(pamonha).not.toHaveTextContent("não está mais à venda");
  });

  it("campanha que acabou (404) ou mudou (campaign_changed): mensagem clara, sem pagar nada", async () => {
    const create = vi.spyOn(api.public, "createOrder").mockResolvedValueOnce(problem("not_found", 404)).mockResolvedValueOnce(problem("campaign_changed", 409));
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    await toReview(user);
    await user.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent("não está mais à venda");
    await user.click(submit());
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/A campanha mudou enquanto você montava o pedido/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pague com Pix" })).not.toBeInTheDocument();
  });

  it("campo de identificacao recusado volta para a etapa dos dados", async () => {
    vi.spyOn(api.public, "createOrder").mockResolvedValue(problem("validation_error", 422, { fields: [{ field: "contributor_email", code: "invalid" }] }));
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    await toReview(user);
    await user.click(submit());

    expect(await screen.findByRole("heading", { name: "Quem está contribuindo?" })).toBeInTheDocument();
    expect(screen.getAllByText("Confira este campo.").length).toBeGreaterThan(0);
  });

  it("sem campos de identificacao visiveis, pula direto da escolha para a revisao", async () => {
    const hidden = { ...SCHOOL, identification: { guardianName: "HIDDEN", studentName: "HIDDEN", classroom: "HIDDEN", contributorEmail: "HIDDEN", contributorPhone: "HIDDEN" } as const };
    render(<CampaignOrderFlow school={hidden} campaign={publicCampaign({ items: [publicItem()] })} />);
    const user = userEvent.setup();
    expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === "Etapa 1 de 3: Produtos")).toBeInTheDocument();
    await add(user, "Cachorro-quente");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("heading", { name: "Confira antes de pagar" })).toBeInTheDocument();
  });

  it("o resumo ao lado acompanha o carrinho", async () => {
    render(<CampaignOrderFlow school={SCHOOL} campaign={publicCampaign()} />);
    const user = userEvent.setup();
    const summary = screen.getByRole("complementary", { name: "Resumo do pedido" });
    expect(summary).toHaveTextContent("Escolha os produtos para começar.");
    await add(user, "Cachorro-quente", 2);
    expect(summary).toHaveTextContent("2 × Cachorro-quente");
    expect(summary).toHaveTextContent("R$ 16,00");
  });
});
