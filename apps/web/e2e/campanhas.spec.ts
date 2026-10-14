import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { CARLA, ELISA, PAULA, apiAcceptsThisOrigin, demoPassword, loginAs, openMenuIfNeeded, uniqueTag } from "./auth-helpers";

/**
 * Campanhas contra a API REAL: a gestao cria uma campanha com produtos e imagens e a poe a venda; a familia a ve na
 * pagina da escola, monta o carrinho e paga pelo Pix (o sandbox); o comprovante lista o que comprou; a gestao ve o
 * pedido pago; encerrada, a campanha some da pagina. Precisa da API com o seed, do site numa porta que a API aceita
 * (E2E_BASE_URL) e da senha de demonstracao (e2e/auth-helpers.ts). Cria dados com titulo unico: o banco e
 * compartilhado. Serial e so no chromium-desktop: os passos dependem uns dos outros e criam dados.
 */
test.describe.configure({ mode: "serial" });
test.skip(!demoPassword() || !apiAcceptsThisOrigin(), "precisa da senha de demonstracao e de E2E_BASE_URL aceita pela API");
test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "cria dados: roda uma vez, em chromium-desktop");
});

const title = uniqueTag("E2E campanha");
// Um PNG de 1x1 pixel valido: a API refaz o arquivo sem metadados e o navegador consegue mostrar.
const PNG_1X1 = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const SCHOOL = "/escola/demo-aurora";

const row = (page: Page, text: string) => page.getByRole("listitem").filter({ hasText: text });

async function axe(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"]).analyze();
  return results.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`);
}

test("gestao: cria a campanha, poe os produtos e as imagens, confere a previa e poe a venda", async ({ page }) => {
  await loginAs(page, CARLA.email);
  await openMenuIfNeeded(page);
  await page.getByRole("link", { name: "Campanhas" }).first().click();
  await expect(page).toHaveURL(/\/painel\/personalizacao$/);
  await expect(page.getByRole("heading", { level: 1, name: "Campanhas" })).toBeVisible();

  // titulo e obrigatorio: avisa sem falar com a API
  await page.getByRole("button", { name: "Nova campanha" }).click();
  const form = page.getByRole("dialog", { name: "Nova campanha" });
  await expect(form).toBeVisible();
  expect(await axe(page), "axe com a janela aberta").toEqual([]);
  await form.getByRole("button", { name: "Criar rascunho" }).click();
  await expect(form.getByText("Escreva o título da campanha.")).toBeVisible();

  await form.getByLabel("Título").fill(title);
  await form.getByLabel(/Texto para as famílias/).fill("Barracas, jogos e a camiseta da turma.");
  await form.getByRole("button", { name: "Criar rascunho" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Campanha criada como rascunho" })).toBeVisible();
  const card = row(page, title);
  await expect(card).toContainText("Rascunho");
  const editor = card.getByRole("heading", { name: "Texto e datas" });
  await expect(editor).toBeVisible();

  // sem produto nenhum a API recusa pôr à venda e o texto explica
  await card.getByRole("button", { name: "Pôr à venda" }).click();
  await page.getByRole("dialog", { name: "Pôr à venda" }).getByRole("button", { name: "Pôr à venda" }).click();
  await expect(card.getByRole("alert")).toContainText("pelo menos um produto");

  // produtos: cada um abre a janela de formulario, no mesmo modelo da contribuicao em dinheiro
  await card.getByRole("button", { name: "Novo produto" }).click();
  const add = page.getByRole("dialog", { name: "Adicionar produto" });
  await expect(add).toBeVisible();
  expect(await axe(page), "axe com a janela de produto aberta").toEqual([]);
  await add.getByLabel("Nome do produto").fill("Cachorro-quente");
  await add.getByLabel("Preço").fill("800");
  await add.getByLabel(/Limite por pedido/).fill("5");
  await add.getByRole("button", { name: "Adicionar produto" }).click();
  await expect(add).toHaveCount(0);
  await expect(card.getByRole("list", { name: "Produtos da campanha" })).toContainText("Cachorro-quente");
  await expect(card.getByRole("list", { name: "Produtos da campanha" })).toContainText("R$ 8,00");
  await card.getByRole("button", { name: "Novo produto" }).click();
  const add2 = page.getByRole("dialog", { name: "Adicionar produto" });
  await add2.getByLabel("Nome do produto").fill("Pamonha");
  await add2.getByLabel("Preço").fill("650");
  await add2.getByRole("button", { name: "Adicionar produto" }).click();
  await expect(card.getByRole("list", { name: "Produtos da campanha" })).toContainText("R$ 6,50");

  // capa e imagem de um produto (a API tira os metadados e o navegador a le de volta com a sessao)
  await card.getByLabel("Arquivo da capa da campanha").setInputFiles({ name: "capa.png", mimeType: "image/png", buffer: PNG_1X1 });
  await expect(page.getByRole("status").filter({ hasText: "Capa salva." })).toBeVisible();
  await card.getByRole("button", { name: "Editar o produto Cachorro-quente" }).click();
  const itemForm = page.getByRole("dialog", { name: "Editar produto" });
  await itemForm.getByLabel("Arquivo da imagem do produto Cachorro-quente").setInputFiles({ name: "hotdog.png", mimeType: "image/png", buffer: PNG_1X1 });
  await expect(page.getByRole("status").filter({ hasText: "Imagem do produto salva." })).toBeVisible();
  await itemForm.getByRole("button", { name: "Cancelar" }).click();
  await expect(card.getByAltText("Capa da campanha").first()).toBeVisible();

  // a previa mostra o que a familia vai ver
  const preview = card.getByRole("group", { name: "Pré-visualização da página da campanha" });
  await expect(preview).toContainText(title);
  await expect(preview).toContainText("Cachorro-quente");
  await expect(preview).toContainText("R$ 6,50");
  expect(await axe(page), "axe com o editor aberto").toEqual([]);

  // ainda e rascunho: a familia nao ve
  const anonymous = await page.context().browser()!.newContext({ baseURL: process.env.E2E_BASE_URL });
  const visitor = await anonymous.newPage();
  await visitor.goto(SCHOOL);
  await expect(visitor.getByRole("heading", { name: "Quanto você quer contribuir?" })).toBeVisible();
  await expect(visitor.getByText(title)).toHaveCount(0);
  await anonymous.close();

  await card.getByRole("button", { name: "Pôr à venda" }).click();
  await page.getByRole("dialog", { name: "Pôr à venda" }).getByRole("button", { name: "Pôr à venda" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Campanha à venda." })).toBeVisible();
  await expect(card).toContainText("À venda");
});

test("familia: ve a campanha na pagina da escola, monta o carrinho, paga pelo Pix e o comprovante lista o pedido", async ({ page }) => {
  const orders: Array<{ body: string; key: string | undefined }> = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/orders")) orders.push({ body: r.postData() ?? "", key: r.headers()["idempotency-key"] });
  });

  await page.goto(SCHOOL);
  // a vitrine fica na aba "Campanhas" (a outra aba e a contribuicao mensal)
  await page.getByRole("tab", { name: "Campanhas" }).click();
  await expect(page.getByRole("heading", { name: "Campanhas da escola" })).toBeVisible();
  const shelf = page.getByRole("listitem").filter({ hasText: title });
  await expect(shelf).toContainText("2 produtos");
  await expect(shelf.locator("img")).toHaveCount(1); // a capa publica
  await expect(shelf.locator("img")).toHaveJSProperty("complete", true);
  expect(await shelf.locator("img").evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0); // e ela abriu de verdade
  expect(await axe(page), "axe com a vitrine").toEqual([]);
  await shelf.getByRole("link").click();

  await expect(page).toHaveURL(new RegExp(`${SCHOOL}/campanha/[0-9a-f-]{36}$`));
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Escolha os produtos" })).toBeVisible();
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByText("Escolha pelo menos um produto.")).toBeVisible();

  const hotDog = page.getByRole("button", { name: "Adicionar um Cachorro-quente" });
  await hotDog.click();
  await hotDog.click();
  await page.getByRole("button", { name: "Adicionar um Pamonha" }).click();
  await expect(page.getByText("3 itens")).toBeVisible();
  await expect(page.getByText("R$ 22,50").first()).toBeVisible(); // 2 x 8,00 + 6,50
  expect(await axe(page), "axe com o carrinho").toEqual([]);
  await page.getByRole("button", { name: "Continuar" }).click();

  await page.getByLabel(/Nome do responsável/).fill("Maria E2E");
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByRole("heading", { name: "Confira antes de pagar" })).toBeVisible();
  const review = page.getByRole("list", { name: "Resumo da contribuição" });
  await expect(review).toContainText("2 × R$ 8,00");
  await expect(review).toContainText("1 × R$ 6,50");
  await page.getByRole("button", { name: /Gerar Pix de R\$ 22,50/ }).click();

  await expect(page.getByRole("heading", { name: "Pague com Pix" })).toBeVisible();
  expect(await page.getByLabel("Pix copia e cola").inputValue()).toMatch(/^PIX-SANDBOX:[0-9a-f]+:2250$/);
  // o pedido foi com os produtos e as quantidades, sem preco nem total, e a chave de idempotencia no cabecalho
  expect(orders).toHaveLength(1);
  expect(orders[0]!.key).toMatch(/^[0-9a-f-]{36}$/);
  expect(orders[0]!.body).not.toMatch(/price|total|amount/i);
  expect(JSON.parse(orders[0]!.body).lines).toHaveLength(2);

  await page.getByRole("button", { name: "Simular pagamento (somente desenvolvimento)" }).click();
  await expect(page.getByRole("heading", { name: "Pagamento confirmado" })).toBeVisible({ timeout: 20_000 });
  await page.getByRole("link", { name: "Ver comprovante" }).click();

  await expect(page.getByRole("heading", { name: "Contribuição confirmada" })).toBeVisible();
  const receipt = page.getByRole("list", { name: "Produtos do pedido" });
  await expect(page.locator("main")).toContainText(`Comprovante de pedido · ${title}`);
  await expect(receipt).toContainText("2 × Cachorro-quente");
  await expect(receipt).toContainText("R$ 16,00");
  await expect(receipt).toContainText("1 × Pamonha");
  await expect(page.locator("main")).toContainText("R$ 22,50");
  // o token so vive na URL
  const token = new URL(page.url()).pathname.split("/").pop()!;
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  expect(stored).not.toContain(token);
  expect(stored).not.toContain(orders[0]!.key!);
  await page.reload();
  await expect(page.getByRole("list", { name: "Produtos do pedido" })).toContainText("2 × Cachorro-quente");
});

test("gestao: ve o pedido pago na campanha; um preco novo vale so para os proximos; encerrar tira da pagina da escola", async ({ page, browser }) => {
  await loginAs(page, CARLA.email);
  await page.goto("/painel/personalizacao");
  const card = row(page, title);
  await expect(card).toContainText("1 pedido pago");
  await expect(card).toContainText("R$ 22,50");

  // o preco muda: o pedido que ja foi feito nao muda e o proximo paga o preco novo
  await card.getByRole("button", { name: `Abrir a campanha ${title}` }).click();
  await card.getByRole("button", { name: "Editar o produto Pamonha" }).click();
  const form = page.getByRole("dialog", { name: "Editar produto" });
  await form.getByLabel("Preço").fill("1000");
  await form.getByRole("button", { name: "Salvar produto" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Produto salvo." })).toBeVisible();
  await expect(card.getByRole("list", { name: "Produtos da campanha" })).toContainText("R$ 10,00");
  await expect(card).toContainText("1 pedido pago");
  await expect(card).toContainText("R$ 22,50"); // o que o pedido pago trouxe nao mudou

  const visitor = await (await browser.newContext({ baseURL: process.env.E2E_BASE_URL })).newPage();
  await visitor.goto(SCHOOL);
  await visitor.getByRole("listitem").filter({ hasText: title }).getByRole("link").click();
  await expect(visitor.getByRole("list", { name: "Produtos da campanha" })).toContainText("R$ 10,00");

  // encerrar e definitivo e tira a campanha da pagina da escola (o 404 e o mesmo de uma que nunca existiu)
  const campaignUrl = visitor.url();
  await card.getByRole("button", { name: "Encerrar campanha" }).click();
  const confirm = page.getByRole("dialog", { name: "Encerrar campanha" });
  await expect(confirm).toContainText("Encerrar é definitivo");
  await confirm.getByRole("button", { name: "Encerrar de vez" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Campanha encerrada." })).toBeVisible();
  await expect(card).toContainText("Encerrada");
  await expect(card.getByRole("button", { name: "Editar texto e datas" })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Novo produto" })).toHaveCount(0);

  await visitor.goto(SCHOOL);
  await expect(visitor.getByText(title)).toHaveCount(0);
  const gone = await visitor.goto(campaignUrl);
  expect(gone?.status()).toBe(404);
  await visitor.context().close();
});

test("funcionario e leitor nao tem a area Personalizacao", async ({ page }) => {
  await loginAs(page, PAULA.email);
  await expect(page.getByRole("link", { name: "Campanhas" })).toHaveCount(0);
  await page.goto("/painel/personalizacao");
  await expect(page).not.toHaveURL(/personalizacao/); // volta para a area dele
  await page.context().clearCookies();
  await loginAs(page, ELISA.email);
  await expect(page.getByRole("link", { name: "Campanhas" })).toHaveCount(0);
});
