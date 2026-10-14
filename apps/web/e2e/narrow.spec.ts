import { expect, test, type Page } from "@playwright/test";
import { apiAcceptsThisOrigin, demoPassword, loginAs } from "./auth-helpers";

/**
 * N5 e N4: telas estreitas (320 e 360 px) sem rolagem horizontal nem rotulo truncado, payload do Pix
 * que quebra entre palavras, cabecalho da entrada que nao pula, e barra superior que nao deixa o
 * conteudo colidir por baixo.
 */
const routes = [
  "/",
  "/escola/demo-aurora",
  "/escola/demo-horizonte",
  "/login",
  "/accept-invitation",
  "/accept-invitation?token=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
  "/escola/nao-existe",
];

// O painel exige sessao: estas rotas so rodam com a API real e a senha de demonstracao (e2e/auth-helpers.ts).
const painelRoutes = [
  "/painel",
  "/painel?tipo=contribuicoes",
  "/painel?tipo=despesas",
  "/painel?tipo=reembolsos",
  "/painel?tipo=devolucoes",
  "/painel/despesas",
  "/painel/solicitacoes",
  "/painel/campanhas",
  "/painel/fechamento",
  "/painel/conta",
];

async function overflow(page: Page) {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const outside: string[] = [];
    for (const el of document.querySelectorAll("body *")) {
      if (el.closest("[class*='sr-only']") || el.closest("svg")) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > vw + 1 || r.left < -1) outside.push(`${el.tagName.toLowerCase()} ${Math.round(r.left)}..${Math.round(r.right)} "${(el.textContent ?? "").trim().slice(0, 24)}"`);
    }
    return { scroll: document.documentElement.scrollWidth - vw, outside: outside.slice(0, 5) };
  });
}

// Precisa da API real (o servidor busca a escola e o POST cria a contribuicao): E2E_BASE_URL=http://127.0.0.1:3102.
async function reachPix(page: Page) {
  await page.goto("/escola/demo-aurora");
  await page.getByRole("radio", { name: /20,00/ }).check({ force: true });
  await page.getByRole("button", { name: "Continuar" }).click();
  await page.getByRole("button", { name: "Continuar" }).click(); // dados opcionais em branco
  await page.getByRole("button", { name: /Gerar Pix/ }).click();
  await expect(page.getByRole("heading", { name: "Pague com Pix" })).toBeVisible();
}

for (const width of [320, 360]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 740 } });

    test("sem rolagem horizontal e sem elemento fora da borda em todas as rotas", async ({ page }) => {
      for (const route of routes) {
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        const o = await overflow(page);
        expect(o, route).toEqual({ scroll: 0, outside: [] });
      }
    });

    test("sem rolagem horizontal e sem elemento fora da borda no painel (logado)", async ({ page }) => {
      test.skip(!demoPassword(), "sem E2E_DEMO_PASSWORD_FILE/E2E_DEMO_PASSWORD");
      await loginAs(page);
      for (const route of painelRoutes) {
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        const o = await overflow(page);
        expect(o, route).toEqual({ scroll: 0, outside: [] });
      }
    });

    test("menu do painel (gaveta): abre, nenhum rotulo truncado e Esc fecha", async ({ page }) => {
      test.skip(!demoPassword(), "sem E2E_DEMO_PASSWORD_FILE/E2E_DEMO_PASSWORD");
      await loginAs(page);
      await page.getByRole("button", { name: "Abrir o menu" }).click();
      const drawer = page.getByRole("dialog", { name: "Menu do painel" });
      await expect(drawer).toBeVisible();
      const labels = await drawer.evaluate((root) =>
        [...root.querySelectorAll<HTMLElement>("nav[aria-label='Seções do painel'] a span, nav[aria-label='Seções do painel'] button span")]
          .filter((el) => el.children.length === 0 && (el.textContent ?? "").trim() !== "")
          .map((el) => ({
            text: el.textContent,
            // "truncate" sempre poe reticencias no CSS; o que importa e o texto realmente cortado
            truncated: el.scrollWidth > el.clientWidth + 0.5,
            fits: el.getBoundingClientRect().right <= document.documentElement.clientWidth,
          })),
      );
      // gestao: Dashboard, Lancamentos do mes (com os 4 tipos), Despesas, Solicitacoes, Campanhas e Fechamento
      const names = labels.map((l) => l.text);
      expect(names).toEqual(expect.arrayContaining(["Dashboard", "Lançamentos do mês", "Despesas", "Solicitações", "Campanhas", "Fechamento"]));
      for (const label of labels) {
        expect(label.truncated, `${label.text} truncado`).toBe(false);
        expect(label.fits, `${label.text} fora da tela`).toBe(true);
      }
      await page.keyboard.press("Escape");
      await expect(drawer).toHaveCount(0);
    });

    test("cartao 'Saldo em caixa' do painel cabe e o numero nao e cortado", async ({ page }) => {
      test.skip(!demoPassword(), "sem E2E_DEMO_PASSWORD_FILE/E2E_DEMO_PASSWORD");
      await loginAs(page);
      await expect(page.getByRole("heading", { name: /saldo em caixa em/i })).toBeVisible();
      const fit = await page.evaluate(() => {
        const title = document.querySelector("#indicators-title")!;
        const card = title.closest("section")!;
        // o <p> logo depois do titulo e o valor (a versao falada fica fora da tela, a visual e o que se mede)
        const number = title.nextElementSibling!.querySelector<HTMLElement>("[aria-hidden='true']")!;
        return { numberRight: number.getBoundingClientRect().right, cardRight: card.getBoundingClientRect().right, scroll: number.scrollWidth - number.clientWidth, vw: document.documentElement.clientWidth };
      });
      expect(fit.scroll).toBeLessThanOrEqual(0);
      expect(fit.numberRight).toBeLessThanOrEqual(fit.cardRight);
      expect(fit.cardRight).toBeLessThanOrEqual(fit.vw);
    });

    test("QR e payload do Pix cabem na tela: sem rolagem horizontal e sem linhas escondidas na caixa do codigo", async ({ page }) => {
      test.skip(!apiAcceptsThisOrigin(), "precisa da API real (E2E_BASE_URL=http://127.0.0.1:3102)");
      await reachPix(page);
      const result = await page.evaluate(() => {
        const textarea = document.querySelector<HTMLTextAreaElement>("#pix-code")!;
        const qr = document.querySelector("svg[role=img]")!.getBoundingClientRect();
        return {
          value: textarea.value,
          overflowX: textarea.scrollWidth - textarea.clientWidth,
          clippedY: textarea.scrollHeight - textarea.clientHeight,
          qrRight: qr.right,
          qrWidth: qr.width,
          vw: document.documentElement.clientWidth,
          pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        };
      });
      expect(result.value).toMatch(/^PIX-SANDBOX:/);
      expect(result.overflowX).toBeLessThanOrEqual(0);
      expect(result.clippedY, "linhas do payload escondidas na caixa").toBeLessThanOrEqual(1);
      expect(result.qrRight).toBeLessThanOrEqual(result.vw);
      expect(result.qrWidth, "QR pequeno demais para ler").toBeGreaterThanOrEqual(200);
      expect(result.pageOverflow).toBeLessThanOrEqual(0);
    });
  });
}

test.describe("cabecalho da entrada nao pula com a API verificando, no ar, fora do ar e nao pronta", () => {
  for (const width of [320, 360, 390, 1440]) {
    test(`${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      let mode: "hold" | "ready" | "down" | "not-ready" = "hold";
      const held: Array<() => void> = [];
      await page.route("**/api/health/ready", async (route) => {
        if (mode === "hold") await new Promise<void>((resolve) => held.push(resolve));
        if (mode === "down") return route.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error" });
        if (mode === "not-ready") return route.fulfill({ status: 503, contentType: "application/json", body: '{"status":"unavailable"}' });
        return route.fulfill({ status: 200, contentType: "application/json", body: '{"status":"ready"}' });
      });
      await page.goto("/");

      const layout = async () =>
        page.evaluate(() => ({
          header: Math.round(document.querySelector("header")!.getBoundingClientRect().height * 10) / 10,
          h1: Math.round(document.querySelector("h1")!.getBoundingClientRect().top * 10) / 10,
          main: Math.round(document.querySelector("main")!.getBoundingClientRect().top * 10) / 10,
          scroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        }));
      const state = () => page.locator("[role=status][data-state]").first();

      await expect(state()).toHaveAttribute("data-state", "checking");
      const checking = await layout();

      mode = "ready";
      held.splice(0).forEach((release) => release());
      await expect(state()).toHaveAttribute("data-state", "ready");
      const ready = await layout();

      mode = "down";
      await page.evaluate(() => window.dispatchEvent(new Event("online")));
      await expect(state()).toHaveAttribute("data-state", "unavailable");
      await expect(page.getByRole("button", { name: "Tentar de novo" })).toBeVisible();
      const down = await layout();

      mode = "not-ready";
      await page.getByRole("button", { name: "Tentar de novo" }).click();
      await expect(state()).toContainText("API indisponível");
      const notReady = await layout();

      for (const [name, l] of [["no ar", ready], ["fora do ar", down], ["nao pronta", notReady]] as const) {
        expect(l, `layout ${name} x verificando`).toEqual(checking);
      }
      expect(checking.scroll).toBeLessThanOrEqual(0);
      // o botao de tentar de novo continua com alvo de 44px mesmo so com o icone
      const box = await page.getByRole("button", { name: "Tentar de novo" }).boundingBox();
      expect(box!.width).toBeGreaterThanOrEqual(43.5);
      expect(box!.height).toBeGreaterThanOrEqual(43.5);
    });
  }
});

test.describe("N4: barra de navegacao fixa nunca fica transparente", () => {
  // O redesenho (Figma) usa barras solidas: o menu lateral e o cabecalho do painel sao opacos. Ainda assim a regra vale
  // para QUALQUER cabecalho, menu ou lateral fixo (sticky/fixed): alpha de base >= 0,9, para o texto que passa por
  // baixo nao colidir. O site e claro de proposito: o esquema escuro do sistema nao muda isso.
  for (const scheme of ["light", "dark"] as const) {
    test(`alpha de base >= 0,9 (${scheme}) no portal da escola e no painel`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      const routes = ["/escola/demo-aurora"];
      if (demoPassword()) {
        await loginAs(page);
        routes.push("/painel");
      }
      for (const route of routes) {
        await page.goto(route);
        const alphas = await page.evaluate(() =>
          [...document.querySelectorAll("header, nav, aside")]
            .filter((el) => ["sticky", "fixed"].includes(getComputedStyle(el).position))
            .map((el) => {
              const m = /rgba?\(([^)]+)\)/.exec(getComputedStyle(el).backgroundColor);
              const parts = m![1]!.split(/[,\s/]+/).filter(Boolean);
              return parts.length >= 4 ? parseFloat(parts[3]!) : 1;
            }),
        );
        if (route === "/painel") expect(alphas.length, `${route}: o painel tem uma barra fixa (menu lateral ou cabecalho)`).toBeGreaterThan(0);
        for (const alpha of alphas) expect(alpha, `${route} ${scheme}`).toBeGreaterThanOrEqual(0.9);
      }
    });
  }
});
