# apps/web — APM Digital (interface)

Next.js (App Router) + TypeScript strict + Tailwind CSS v4. Só UI: nenhuma regra financeira mora
aqui. O frontend **nunca decide que um Pix foi pago**; ele mostra o status que a camada de dados
devolve.

## Rodar

```bash
cd apps/web
cp .env.example .env.local   # opcional: só tem API_PROXY_URL
npm ci
npm run dev                  # http://127.0.0.1:3101
```

Produção local (a "prévia"):

```bash
npm run build
npm run start -- -p 3100     # o script start já embute -H 127.0.0.1: não abre a rede sozinho
```

Para expor de propósito (por exemplo, dentro de um container atrás do proxy reverso), passe o host
no comando: `npm run start -- -H 0.0.0.0 -p 3000`. O último `-H` vence.

| Script | O que faz |
|---|---|
| `npm run dev` | servidor de desenvolvimento em 127.0.0.1:3101 |
| `npm run build` / `start` | build e servidor de produção (`start` só liga em 127.0.0.1) |
| `npm run lint` | ESLint |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest + Testing Library (inclui os guardas de CSS/animação) |
| `npm run test:e2e` | Playwright em WebKit e Chromium (precisa de `npx playwright install webkit chromium` uma vez) |

## Variáveis de ambiente

- `API_PROXY_URL` (padrão `http://127.0.0.1:8001`): destino do rewrite de `/api/*`. É lida **no
  build** (o Next compila os rewrites). Sem segredos, e nunca `NEXT_PUBLIC_*`.

## Dados: o que é real e o que é simulado

- **Real**: `GET /api/health/ready` (chip de status da API) e a **autenticação** (`src/lib/api/auth.ts`,
  contrato em `docs/auth.md`): `POST /api/v1/auth/login`, `logout`, `GET /auth/me`, `POST /auth/context`,
  `POST /auth/password` e `POST /api/v1/invitations/accept`. O navegador só chama `/api/*` na mesma
  origem; não há CORS nem requisição a terceiros.
  - A sessão é um cookie **HttpOnly** (`apm_session`; `__Host-apm_session` em produção) que o site nunca
    lê. O token CSRF vem do cookie legível `apm_csrf` e vai em `X-CSRF-Token` em todo pedido que muda
    dados. A API só aceita esses pedidos das origens listadas em `PUBLIC_ORIGINS` (`.env` da raiz, lido pelo
    `docker-compose`): por padrão `127.0.0.1:3101`/`localhost:3101` (dev) e `:3100` (prévia). Para abrir o site
    em outra porta (ex.: `npm run dev -- -p 3102`), acrescente `http://127.0.0.1:3102,http://localhost:3102` a
    `PUBLIC_ORIGINS` e recrie a API (`docker compose up -d --no-deps --force-recreate api`).
  - `/painel` exige sessão: o **servidor do Next** repassa o cookie a `GET /api/v1/auth/me`
    (`src/lib/api/server.ts`); sem sessão, redireciona para `/login`. API fora do ar não é logout: mostra
    "Não foi possível abrir o painel".
  - O seletor do painel lista os **vínculos reais** da pessoa (cada um é de UMA escola: não existe vínculo
    de rede, ADR-020) e troca por `POST /auth/context`; o cliente nunca define organização nem escola. Sessão sem vínculo ativo mostra a escolha antes do painel.
  - Os textos de erro vêm do `code` do `problem+json` (`src/lib/auth-messages.ts`); o `title`/`detail` do
    servidor nunca aparece. `/login?next=` só aceita `/painel` e o link do convite (lista fechada).
  - `POST /auth/password` tem cliente e testes, mas **ainda não tem tela**.
- **Portal público (REAL)**, `/escola/{slug}` (`/apm/{slug}` redireciona), contrato em `docs/public-flow.md`
  (`src/lib/api/public.ts`): escola, campos de identificação (`REQUIRED`/`OPTIONAL`/`HIDDEN`), criação da
  contribuição com `Idempotency-Key` (uma `crypto.randomUUID()` por tentativa, só em memória e no cabeçalho),
  QR Code desenhado no navegador a partir de `emv_payload` (`qrcode` 1.5.4, sem chamada externa), polling de 2 s
  com recuo, `PAID`/`REVIEW_REQUIRED`/QR expirado (novo QR) e comprovante em `/escola/{slug}/pedido/{token}`.
  O site só mostra "pago" quando a **contribuição** vem `PAID` da API. Com payload `PIX-SANDBOX:` (só em
  desenvolvimento) aparece "Simular pagamento", que chama `POST /api/v1/dev/sandbox/pix/{txid}/pay`.
- **Painel (REAL)**, `docs/statement.md` (`src/lib/api/statement.ts`): para a escola do vínculo ativo
  (`active_membership.school.id`), resumo do mês com os dois saldos (em caixa, e após reembolsos pendentes),
  lançamentos por tipo com "carregar mais" (cursor), pendências fora do saldo, mês na URL (`?mes=YYYY-MM`),
  "Registrar contribuição em dinheiro" (`contributions:record_cash`) e link do PDF das contribuições do mês.
  Rota que responder 403 (o `viewer` só lê o resumo) vira aviso. Todo vínculo é de uma escola, então o painel
  sempre mostra os números dela. Quem tem 2 ou mais vínculos escolhe o contexto como antes.
- **Despesas (REAL)**, `/painel/despesas`, `docs/expenses.md` (`src/lib/api/expenses.ts`): o funcionário vê só
  "Minhas despesas" (lista com status em português, formulário com anexo multipart, enviar, cancelar, motivo da
  correção pedida); a gestão vê a fila de análise (filtro por situação na API) e age conforme a permissão da
  sessão: aprovar (inclusive parcial, só quando um colaborador pagou, com motivo), recusar, pedir correção
  (motivo), registrar reembolso ou pagamento. Não se oferece ao **autor** o que a API recusa (aprovar, recusar,
  pedir correção, reembolsar, pagar a própria despesa); o servidor continua a autoridade (403, 404, 409, 422 em
  português). A API devolve só o **id** de quem enviou, não o nome. Anexos: só PNG, JPEG, WebP e PDF até 10 MB; a
  API não tem rota para remover anexo, então "trocar" é anexar o novo. O download passa pela API (cookie de
  sessão), nunca URL pública.
- **Fechamento mensal (REAL)**, `/painel/fechamento`, `docs/statement.md` (`src/lib/api/closings.ts`): lista com
  estado (fechado ou reaberto), números congelados com os dois saldos, diferença para o banco e código de
  verificação, "Fechar mês" (mês e saldo do banco em centavos; a API exige ordem e mostra o próximo mês),
  "Verificar", "Baixar PDF do extrato mensal" (só de fechamento ativo; reaberto não tem PDF) e "Reabrir mês" só
  para quem tem `months:reopen` (o administrador da escola), com motivo de 10 a 500 caracteres. O
  viewer só lê. O "PDF das contribuições do mês" segue no Resumo.
- **Solicitações (REAL)**, `/painel/solicitacoes`, `docs/staff-requests.md` (`src/lib/api/staff-requests.ts`): o
  funcionário abre pedidos para a gestão ("Nova solicitação": categoria, título, descrição e até 6 fotos); a gestão
  tem a caixa de entrada (filtros de situação e categoria na API), inicia o atendimento e resolve com uma nota que o
  autor lê; o autor cancela enquanto está aberto. O administrador da escola vê as duas abas (`?aba=minhas`). As
  fotos vão em multipart e voltam pela API com a sessão (nunca há URL pública). O menu mostra "Solicitações" a
  quem tem `requests:read_all` e "Minhas solicitações" a quem só abre pedidos.
- **Fotos** (`PhotoPicker`, `CameraDialog`, `src/lib/photo.ts`): "Tirar foto" usa a câmera do navegador
  (`getUserMedia`, câmera traseira quando há; sem ela, o campo `capture` do sistema) e "Escolher da galeria" aceita
  PNG, JPEG e WebP. A foto é reduzida no navegador (lado maior de 2400 px, JPEG) para caber nos 10 MB e fica só na
  memória até o envio. A câmera exige `Permissions-Policy: camera=(self)` (`next.config.ts`; antes era `camera=()`).
  Uma janela aberta por cima de outra (a câmera sobre o formulário) é tratada pelo `Modal`: só a do topo responde a
  Esc e Tab. Nos e2e o Chromium usa a câmera de mentira (`playwright.config.ts`).
- **Alterar senha (REAL)**, `/painel/conta`, `POST /auth/password`: 12 a 128 caracteres e diferente da atual; a
  API encerra as outras sessões e abre uma nova neste navegador.
- **Menu por perfil**, a partir de `active_membership.permissions` (`src/lib/permissions.ts`): funcionário =
  "Minhas despesas"; gestão e direção = Resumo, Despesas e Fechamento; viewer = Resumo e Fechamento (leitura).
  Os lançamentos por tipo (contribuições, despesas, reembolsos, devoluções) ficam em links dentro do Resumo.
- **Simulado**: nada. Não há mais camada de mocks nem selo de protótipo. Ainda **sem tela**: administração
  (escolas, categorias, convites de usuário).

Usuários de demonstração (dados falsos) e a senha do seed ficam fora do repositório. Testes de unidade
usam mocks; o e2e com login real lê a senha só em tempo de execução (`E2E_DEMO_PASSWORD_FILE`, veja
`e2e/auth-helpers.ts`) e roda contra o `npm run dev` (3101), porque a API só aceita as origens acima.

Rotas: `/` · `/escola/[slug]` · `/escola/[slug]/pedido/[token]` · `/login` · `/accept-invitation?token=…` · `/painel` (exige sessão) · `/painel/despesas` · `/painel/fechamento` · `/painel/conta`.
Escolas de demonstração (banco local): `demo-aurora`, `demo-horizonte`, `demo-central`.

## Design (Figma "APM Digital")

O visual segue o arquivo do Figma (login, painel da gestão, janela de contribuição em dinheiro e fluxo das famílias).
As telas que o Figma não tem (Fechamento, Alterar senha, Pix, comprovante, erro, 404, convite) usam o mesmo padrão.

- **Fonte:** 42dot Sans (SIL OFL, `src/app/fonts/OFL.txt`), arquivo variável servido pelo próprio site via
  `next/font/local` (a CSP só aceita `font-src 'self'`; nada vem de terceiros). Pesos 300 a 800.
- **Tokens:** `src/app/globals.css`. Paleta da marca (`brand-900` … `brand-200`, a paleta "fknelo" do Figma), degradês
  (`bg-grad-brand`, `bg-grad-chip`), raios (`--r-ctl` 18, `--r-lg` 26, `--r-xl` 34), escala tipográfica fluida
  (`text-display`, `text-title`, `text-kpi`…) e as cores do gráfico (`--series-*`, medidas no Figma).
- **Tema:** o Figma só tem tema claro, então o site é claro de propósito (`color-scheme: light`), sem tema escuro.
  A cor da escola (`accentColor` da API) não pinta mais o portal: a escola aparece pelo nome.
- **Assets:** `public/brand/` (logo claro e escuro, halftone com transparência, arte do login, ilustrações 3D),
  todos exportados do Figma, aparados e comprimidos. O halftone é a classe `.halftone` (enfeite atrás do conteúdo).
  Ícones: Bootstrap Icons (a família usada no Figma, MIT) em `components/ui/icons.tsx`.
- **Responsivo:** o Figma tem um tamanho por tela (1712 px na gestão, 1607 px no login, 580 px na família). As outras
  larguras foram derivadas: menu lateral recolhível no desktop e gaveta no celular, gráfico em colunas (largo) ou em
  barras horizontais (estreito), janelas viram folha inferior no celular. Verificado de 320 a 1440 px.
- **Dados do dashboard:** "Composição do saldo", "Saídas pagas" e os quatro números vêm de `GET .../statement/summary`;
  as pendências, de `GET .../statement/pending`. Nada é digitado nem simulado.

## Estrutura

```
src/app/          rotas (App Router)
src/components/   ui/, portal/, painel/, despesas/, fechamento/, conta/, status/, login/, invitation/
src/lib/          money (centavos + BRL), validation, status, color (contraste AA), api/ (health, auth, public, statement, expenses, closings, csrf, server), auth-messages, expense-labels, permissions, download, safe-next, roles, hooks/
src/proxy.ts      CSP com nonce por requisição
```

## Segurança

- CSP restritiva por requisição (`src/proxy.ts`): scripts só com nonce, `frame-ancestors 'none'`,
  `object-src 'none'`, sem origens de terceiros. Exceção consciente: `style-src-attr 'unsafe-inline'`,
  porque a cor da escola é aplicada como variáveis CSS num atributo `style` (renderizado no servidor).
- `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `X-Frame-Options`, `Permissions-Policy`
  e `poweredByHeader` desligado (`next.config.ts`). HSTS fica com o proxy reverso (HTTPS).
- O matcher do `proxy.ts` exclui só `/api`, `/api/*` e os estáticos: `/apix`, `/api-docs` e `/apiary`
  recebem a CSP com nonce (testado em unidade e em e2e).
- Páginas de erro (`error.tsx`, `global-error.tsx`) em português, sem expor `error.message`.
- Sem `dangerouslySetInnerHTML` (regra de lint). Sem segredos e sem `NEXT_PUBLIC_*`.
- Em produção, o proxy reverso não deve sobrescrever o `Content-Security-Policy` das páginas.

## Comprovante e privacidade (dado de criança)

- **O comprovante só afirma o que a API confirma.** O servidor do Next consulta `GET .../receipt`: `200` entrega o
  comprovante; `409` mostra "ainda não confirmado"; o `404` único da API (token inexistente, de outra escola ou
  malformado) vira a 404 do site; qualquer outra falha (429, API fora do ar) deixa o HTML **neutro** ("Conferindo seu
  comprovante": sem "Pago", sem nome, sem valor) e o navegador tenta de novo.
- O token da contribuição (segredo da família) só vive na memória da página do fluxo e na URL do comprovante; a
  `Idempotency-Key` é tão secreta quanto ele e só vai no cabeçalho do POST. Nada vai para `localStorage`,
  `sessionStorage`, URL de outra página nem log. O navegador não guarda dado pessoal.
- A API conta consultas que erram (token ou slug inexistente) contra o endereço e responde `429` com `Retry-After`;
  o site mostra um aviso com o tempo de espera (no polling, espera e tenta de novo). Rodar muitos e2e seguidos
  contra a mesma API pode bloquear o endereço por alguns minutos.
- Nenhum `<form>` cai em GET com dados na URL (todos `method="post"` com `preventDefault`); campos de nome
  sem corretor ortográfico (`spellcheck=false`) e aluno/turma sem autopreenchimento.
- Colar no campo de valor interpreta **reais** (`1.000` = R$ 1.000,00, `1,50` = R$ 1,50); o que não é
  valor é ignorado com um aviso curto. Digitar continua com a máscara de caixa eletrônico.

## Animações são melhoria progressiva (WebKit, portal do Maestri)

O estado base de **todo** conteúdo é visível. O WebKit **congela a linha do tempo das animações** com o
documento oculto (aba em segundo plano, portal do Maestri, WKWebView fora da tela): uma animação de
entrada parada em `t=0` mantém o keyframe inicial para sempre, e `opacity: 0` vira conteúdo invisível
(foi o defeito da rodada 1). Por isso:

- nenhum `@keyframes` parte de `opacity: 0` (só `transform` ou traçado decorativo);
- toda animação de entrada só existe sob `[data-motion="on"]`, que o `MotionGate` liga **apenas** com o
  documento visível; oculto, o conteúdo aparece direto no estado final;
- as animações de passo só rodam depois de uma ação do usuário, nunca no carregamento da página;
- o carimbo "Pago" entra por escala (nunca por `stroke-dashoffset`): congelado em qualquer ponto, o símbolo
  continua visível;
- o polling do chip da API não para com o documento oculto, só fica mais lento (60 s).

Guardas (Vitest): `src/app/motion-css.test.ts` + `src/test-utils/css-guard.ts` (opacity 0/0%, visibility,
escala < 0,1, translate fora da tela, clip-path, content-visibility e tamanho 0, no keyframe inicial e no
estado base, com testes de mutação), `src/hidden-content-sources.test.ts` (utilitários Tailwind que
escondem e o `MotionGate` no layout). Guardas (e2e, **com a CSP real ativa**, sem `bypassCSP`):
`e2e/visible-content.spec.ts` em WebKit e Chromium nos cenários `normal`, `frozen` (toda `CSSAnimation`
pausada em t=0 por Web Animations) e `hidden` (documento oculto + linha do tempo congelada, como o portal
do Maestri; exige `data-motion` desligado e zero animação de entrada). Falha se algum texto visível ficar
com opacidade efetiva < 0,9, se o carimbo SVG (anel/check) sumir ou se houver violação de CSP.
`e2e/detectors.spec.ts` testa os próprios detectores.

Observação para quem testa pelo portal do Maestri: a CSP de produção não permite `eval`, então
`maestri portal evaluate` não funciona na prévia (3100); `snapshot`, `click`, `fill` e `screenshot`
funcionam. Para `evaluate`, use o `npm run dev` (3101).

## Acessibilidade e movimento

Foco visível, alvos de toque de 44px, rótulos e `aria-live` nas mudanças de status, contraste AA
em claro e escuro (a cor da escola é recalculada em `src/lib/color.ts`) e `prefers-reduced-motion`
respeitado. O único momento orquestrado é o carimbo "Pago", quando a camada de dados devolve `PAID`.
