import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { CARLA, ELISA, PAULA, apiAcceptsThisOrigin, demoPassword, loginAs, openMenuIfNeeded, uniqueTag } from "./auth-helpers";

/**
 * Solicitacoes contra a API REAL: o funcionario abre um pedido com uma foto da galeria e uma tirada na hora
 * (camera de mentira do Chromium), a gestao inicia e resolve com uma nota, e o funcionario le a resposta. Precisa
 * da API com o seed, do site numa porta que a API aceita (E2E_BASE_URL) e da senha de demonstracao
 * (e2e/auth-helpers.ts). Cria dados com titulo unico: o banco e compartilhado. Serial e so no chromium-desktop:
 * os passos dependem uns dos outros, criam dados e a camera de mentira so existe no Chromium.
 */
test.describe.configure({ mode: "serial" });
test.skip(!demoPassword() || !apiAcceptsThisOrigin(), "precisa da senha de demonstracao e de E2E_BASE_URL aceita pela API");
test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "cria dados: roda uma vez, em chromium-desktop");
});

const title = uniqueTag("E2E solicitacao");
// Um PNG de 1x1 pixel valido: a API reconhece o tipo pelos primeiros bytes e o navegador consegue mostrar a previa.
const PNG_1X1 = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

const row = (page: Page, text: string) => page.getByRole("listitem").filter({ hasText: text });

async function axe(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"]).analyze();
  return results.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`);
}

test("funcionario: so as proprias; abre um pedido com foto da galeria e da camera, e ve a lista", async ({ page }) => {
  await loginAs(page, PAULA.email);
  await openMenuIfNeeded(page);
  await page.getByRole("link", { name: "Minhas solicitações" }).first().click();
  await expect(page).toHaveURL(/\/painel\/solicitacoes$/);
  await expect(page.getByRole("heading", { level: 1, name: "Minhas solicitações" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nova solicitação" })).toBeVisible();

  await page.getByRole("button", { name: "Nova solicitação" }).click();
  const form = page.getByRole("dialog", { name: "Nova solicitação" });
  await expect(form).toBeVisible();
  expect(await axe(page), "axe com a janela aberta").toEqual([]);

  // campos obrigatorios: avisa sem falar com a API
  await form.getByRole("button", { name: "Enviar solicitação" }).click();
  await expect(form.getByText("Escolha uma categoria.")).toBeVisible();
  await expect(form.getByText("Escreva o título do pedido.")).toBeVisible();

  await form.getByLabel("Categoria").selectOption("MAINTENANCE");
  await form.getByLabel("Título").fill(title);
  await form.getByLabel(/Descrição/).fill("Torneira do banheiro do segundo andar pingando desde segunda.");
  await form.getByLabel("Escolher fotos da galeria").setInputFiles({ name: "galeria.png", mimeType: "image/png", buffer: PNG_1X1 });
  await expect(form.getByAltText("Foto 1")).toBeVisible();

  // camera: abre por cima do formulario, tira a foto e volta com a segunda previa
  await form.getByRole("button", { name: "Tirar foto" }).click();
  const camera = page.getByRole("dialog", { name: "Tirar foto com a câmera" });
  await expect(camera).toBeVisible();
  const shoot = camera.getByRole("button", { name: "Tirar a foto" });
  await expect(shoot).toBeEnabled({ timeout: 20_000 });
  await shoot.click();
  await expect(camera).toHaveCount(0);
  await expect(form).toBeVisible(); // a janela de baixo continua aberta
  await expect(form.getByAltText("Foto 2")).toBeVisible();

  await form.getByRole("button", { name: "Enviar solicitação" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Solicitação enviada para a gestão." })).toBeVisible();
  const card = row(page, title);
  await expect(card).toContainText("Manutenção");
  await expect(card).toContainText("Aberta");
  await expect(card).toContainText("2 fotos");
  expect(await axe(page), "axe com a lista").toEqual([]);

  // o pedido recem-aberto ja vem com o detalhe aberto; as fotos sao baixadas pela API com a sessao
  await expect(card.getByTestId("request-detail")).toBeVisible();
  await expect(card.getByAltText("Foto 1")).toBeVisible();
  await expect(card.getByAltText("Foto 2")).toBeVisible();
  await expect(card.getByRole("button", { name: "Cancelar solicitação" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Iniciar atendimento" })).toHaveCount(0); // o funcionario nao responde
});

test("gestao: ve o pedido na caixa de entrada, inicia o atendimento e resolve com uma nota; nao abre pedidos", async ({ page }) => {
  await loginAs(page, CARLA.email);
  await openMenuIfNeeded(page);
  await page.getByRole("link", { name: "Solicitações" }).first().click();
  await expect(page).toHaveURL(/\/painel\/solicitacoes$/);
  await expect(page.getByRole("heading", { level: 1, name: "Solicitações" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nova solicitação" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abertas" })).toHaveAttribute("aria-pressed", "true");

  const card = row(page, title);
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: /Abrir detalhes da solicitação/ }).click();
  await expect(card.getByText("Torneira do banheiro do segundo andar")).toBeVisible();
  await card.getByRole("button", { name: "Ver foto 1 em tamanho maior" }).click();
  const big = page.getByRole("dialog", { name: "Foto 1" });
  await expect(big).toBeVisible();
  await big.getByRole("button", { name: "Fechar" }).click();
  await expect(big).toHaveCount(0);

  await card.getByRole("button", { name: "Iniciar atendimento" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Atendimento iniciado." })).toBeVisible();
  // saiu de "Abertas": agora esta em andamento
  await expect(row(page, title)).toHaveCount(0);
  await page.getByRole("button", { name: "Em andamento" }).click();
  const doing = row(page, title);
  await expect(doing).toContainText("Em andamento");
  await doing.getByRole("button", { name: /Abrir detalhes da solicitação/ }).click();
  await doing.getByRole("button", { name: "Marcar como resolvida" }).click();
  await doing.getByLabel(/Resposta para quem pediu/).fill("Encanador chamado, conserto na quarta.");
  await doing.getByRole("button", { name: "Marcar como resolvida" }).last().click();
  await expect(page.getByRole("status").filter({ hasText: "Solicitação resolvida." })).toBeVisible();

  await page.getByRole("button", { name: "Resolvidas" }).click();
  await page.getByLabel("Categoria").selectOption("MAINTENANCE");
  await expect(row(page, title)).toContainText("Resolvida");
  await page.getByLabel("Categoria").selectOption("FINANCE");
  await expect(row(page, title)).toHaveCount(0); // o filtro de categoria funciona na API
});

test("funcionario le a resposta da gestao; o pedido resolvido nao aceita mais foto nem cancelamento", async ({ page }) => {
  await loginAs(page, PAULA.email);
  await page.goto("/painel/solicitacoes");
  const card = row(page, title);
  await expect(card).toContainText("Resolvida");
  await card.getByRole("button", { name: /Abrir detalhes da solicitação/ }).click();
  await expect(card.getByRole("note")).toContainText("Resposta da gestão: Encanador chamado, conserto na quarta.");
  await expect(card.getByRole("button", { name: "Cancelar solicitação" })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Tirar foto" })).toHaveCount(0);
});

test("quem so le o resumo (leitor) nao ve o menu nem entra na area", async ({ page }) => {
  await loginAs(page, ELISA.email);
  await openMenuIfNeeded(page);
  await expect(page.getByRole("link", { name: /Solicitações/ })).toHaveCount(0);
  await page.goto("/painel/solicitacoes");
  await expect(page).toHaveURL(/\/painel$/);
});
