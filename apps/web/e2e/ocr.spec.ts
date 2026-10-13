import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { PAULA, apiAcceptsThisOrigin, demoPassword, loginAs, uniqueTag } from "./auth-helpers";

/**
 * Despesa lida de uma foto de nota (docs/ocr.md) contra a API REAL e o servico OCR REAL em modo `demo`, que le
 * SEMPRE a mesma nota inventada (R$ 87,50, 10/09/2026, PAPELARIA CENTRAL LTDA): o teste prova a cadeia
 * navegador -> API -> servico OCR -> formulario, nao a precisao de um modelo. Precisa da API com
 * OCR_ENABLED=true e do servico `ocr` com OCR_ENGINE=demo na rede dela (docker compose --profile ocr), alem do
 * que os outros testes com login pedem (e2e/auth-helpers.ts). Sem OCR no servidor, os testes sao PULADOS.
 * O que grava (um rascunho) roda so no chromium-desktop e com descricao propria: o banco e descartavel.
 */
test.skip(!demoPassword() || !apiAcceptsThisOrigin(), "precisa da senha de demonstracao e de E2E_BASE_URL aceita pela API");

// Um PNG de 1x1 pixel valido: a API reconhece o tipo pelos primeiros bytes; o conteudo nao importa para o engine `demo`.
const PNG_1X1 = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function axe(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"]).analyze();
  return results.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`);
}

async function openReader(page: Page) {
  await loginAs(page, PAULA.email);
  await expect(page).toHaveURL(/\/painel\/despesas$/);
  await page.getByRole("button", { name: "Nova despesa" }).click();
  await expect(page.getByRole("heading", { name: "Nova despesa" })).toBeVisible();
  const toggle = page.getByRole("button", { name: "Ler a nota (OCR)" });
  // A consulta "o OCR esta ligado?" chega depois do formulario: espera um pouco; sem o botao, o servidor nao tem OCR.
  const offered = await toggle.waitFor({ timeout: 8_000 }).then(() => true, () => false);
  test.skip(!offered, "a leitura da nota esta desligada neste servidor");
  await toggle.click();
  await expect(page.getByRole("button", { name: "Ler a nota", exact: true })).toBeDisabled();
}

test("ler a nota: telas estreitas sem rolagem lateral e sem violacoes de acessibilidade", async ({ page }) => {
  await openReader(page);
  await page.getByLabel("Escolher fotos da galeria").setInputFiles({ name: "nota.png", mimeType: "image/png", buffer: PNG_1X1 });
  await expect(page.getByAltText("Foto 1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ler a nota", exact: true })).toBeEnabled();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "rolagem horizontal").toBeLessThanOrEqual(0);
  expect(await axe(page), "axe com o leitor de nota").toEqual([]);
});

test("ler a nota: a foto vai para a API, o formulario vem preenchido como sugestao e a pessoa salva o rascunho", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "cria dados: roda uma vez, em chromium-desktop");
  const description = uniqueTag("E2E nota lida");
  await openReader(page);
  await page.getByLabel("Escolher fotos da galeria").setInputFiles({ name: "cupom-e2e.png", mimeType: "image/png", buffer: PNG_1X1 });
  await expect(page.getByAltText("Foto 1")).toBeVisible();
  await page.getByRole("button", { name: "Ler a nota", exact: true }).click();

  await expect(page.getByLabel("Valor", { exact: true })).toHaveValue("87,50", { timeout: 20_000 });
  await expect(page.getByLabel("Data da despesa")).toHaveValue("2026-09-10");
  await expect(page.getByLabel(/Fornecedor/)).toHaveValue("PAPELARIA CENTRAL LTDA");
  await expect(page.getByLabel("Descrição")).toHaveValue("Compra em PAPELARIA CENTRAL LTDA");
  await expect(page.getByText("Sugerido pela leitura da nota. Confira.")).toHaveCount(4);
  await expect(page.getByText("Leitura concluída. Confira os campos preenchidos antes de salvar.")).toBeVisible();
  expect(await axe(page), "axe depois da leitura").toEqual([]);

  // a pessoa confere e muda o que quiser: a marca de "sugerido" sai do campo que ela mexeu
  await page.getByLabel("Descrição").fill(description);
  await expect(page.getByText("Sugerido pela leitura da nota. Confira.")).toHaveCount(3);

  await page.getByRole("button", { name: "Salvar rascunho" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Arquivo anexado." })).toBeVisible();
  const saved = page.getByRole("listitem").filter({ hasText: description });
  await expect(saved).toContainText("87,50");
  await expect(saved).toContainText("Rascunho");
});
