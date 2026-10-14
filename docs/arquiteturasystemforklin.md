# Arquitetura do ecossistema Forklin: resumo para construir o MVP do APM Digital

Atualizado em 2026-10-14. Base: leitura do código e dos ADRs de `api_central`, `App_forklin`, `painel-admin` e `DiarioDigital` (branch `integracao`) e do APM neste repositório. Nada foi testado em produção.

## 0. Como ler este documento

Cada afirmação leva uma etiqueta:

- **[HOJE]** existe e foi verificado no código.
- **[PLANEJADO]** foi desenhado, mas não existe.
- **[ABERTO]** depende de decisão do dono do produto.

Instruções para o Claude:

1. Nunca trate [PLANEJADO] como existente. Ao propor ou implementar algo, cite a etiqueta.
2. Leia as seções 1, 6, 9, 10 e 11 antes de planejar qualquer coisa do APM.
3. Em qualquer item da seção 11, pergunte ao dono antes de decidir. O padrão indicado vale só até ele responder.
4. Não implemente nada da seção 10 sem o dono aprovar a ordem.

## 1. Resumo

1. A Forklin vende produtos (Diário Digital, APM Digital, futuros) a **organizações**: o cliente, seja escola, rede ou empresa.
2. Quatro peças: **Admin** (equipe Forklin), **App** (única porta de login), **API Central + Core DB** (identidade, organizações, produtos, vagas, acessos e SSO) e os **produtos** (cada um com banco e regras próprios).
3. A equipe Forklin cria a organização, contrata produtos com limite de vagas e cadastra o primeiro Administrador. Ele cadastra as demais pessoas pelo App.
4. O login existe só no App. Abrir um produto é SSO: código de uso único (60 s) que o produto troca por um JWT assinado (10 min).
5. A Central só sabe que "a pessoa X tem acesso ao produto P com o cargo C". O que C pode fazer é regra do produto.
6. Produto não lê o Core DB nem o banco de outro produto. A Central não guarda dado de produto.
7. Só o Diário está integrado, e atrás de uma flag. O APM tem login, organizações e usuários próprios e **não está integrado** [HOJE].
8. Contratar um produto não cria o espaço do cliente dentro dele [HOJE]. Criar esse espaço ao contratar é [PLANEJADO].
9. O split de pagamento é [PLANEJADO]. No APM só existe Pix por uma interface com sandbox, e o gateway real não foi escolhido.

## 2. Peças [HOJE]

Caminhos relativos a este repositório.

| Peça | Onde | Função | Estado |
| --- | --- | --- | --- |
| Admin | `../../admin` (painel-admin) | Painel da equipe Forklin. Sem login próprio: o Super Admin entra pelo App | existe |
| App | `../../app` (App_forklin) | Login único. Mostra só os produtos liberados. Administradores e Gestores cadastram pessoas aqui | existe |
| API Central + Core DB | `../../api` (api_central) | FastAPI + Postgres `forklin_core`. Faz login, SSO, convites e auditoria | existe |
| Diário Digital | `../DiarioDigital` | Primeiro produto, em produção | SSO atrás de `FORKLIN_CORE_ENABLED` |
| APM Digital | este repositório (`apps/api`, `apps/web`, `apps/ocr`) | Este produto | fora do ecossistema |

Atenção: nos três repositórios da Central, a `main` está atrás de `origin/integracao`. A `main` não tem Administrador nem Gestor. Os clones locais estão na `main`; para ler a versão atual use `git show origin/integracao:<arquivo>`. Não foi verificado se `integracao` já está em produção.

## 3. Modelo de acesso da Central [HOJE]

```
organizations ──< organization_products (contrato, max_users)
      │
      └──< organization_users (role: admin | member) >── users
                                   │
user_products (organização, usuário, produto, role_key, status, is_manager)
```

- O banco garante, por chaves compostas: o usuário pertence à organização, a organização contratou o produto e a role pertence ao produto.
- **Vagas:** acesso ativo e suspenso ocupam vaga; revogado libera. `max_users = 0` significa que ninguém entra.
- **Uma pessoa pertence a uma só organização.** A organização nunca fica sem Administrador.
- **Produto no catálogo:** `slug`, nome, `base_url` (destino do SSO, nunca vindo da requisição) e cargos em snake_case.
- **Convite:** a Central envia o e-mail, com token de uso único válido por 7 dias. A pessoa define a senha e cai no App.

| Papel | Quem | O que pode |
| --- | --- | --- |
| Super Admin | Equipe Forklin | Tudo: organizações, produtos, cargos, contratos e vagas |
| Administrador da empresa | `organization_users.role = admin` | Tudo dentro da própria organização: cadastra pessoas, dá acesso e cargo, marca Gestores, desativa, convida |
| Gestor | `user_products.is_manager`, por produto | Cadastra pessoas e dá cargos só naquele produto. Não nomeia Gestor nem mexe em Administrador |
| Membro | Demais | Entra no App e abre os produtos a que tem acesso |

"Gestor" (poder de cadastrar, definido na Central) e "cargo gestao" (perfil do Diário que só acompanha turmas) são independentes. Ser Administrador não dá acesso a produto sozinho: o acesso é concedido por produto.

**Ordem de cadastro de um cliente [HOJE]:** (1) produto no catálogo, uma vez; (2) organização no Admin; (3) contrato com vagas; (4) primeira pessoa como Administrador, com acesso e cargo no produto; (5) convite por e-mail; (6) o Administrador cadastra o restante pelo App; (7) cada pessoa abre o produto com um clique.

## 4. SSO e contrato Central-produto [HOJE, atrás de flags]

1. No App, "Acessar" chama `POST /launch-codes` (uso único, 60 s). A Central confere acesso, organização ativa e produto ativo, e devolve `{products.base_url}/sso/callback?code=…`.
2. O backend do produto troca o código em `POST /launch-codes/exchange-product` e recebe um JWT EdDSA de 10 minutos.
3. O produto valida o JWT com as chaves de `/.well-known/jwks.json`: `iss=forklin`, `aud=<slug do produto>`. Claims: `sub`, `org`, `role`, `email`, `name`, `org_role`, `is_manager`, `ver=1`.
4. O produto cria a própria sessão. A Central não participa mais.
5. Fluxo inverso, "Entrar com Forklin" a partir do produto: `app/entrar?produto=<slug>&state=<state>`.

Itens opcionais, todos com flag desligada por padrão:

- **API de produto** `/product-api/v1` (`POST /users`, `:batch`, `PATCH`), autenticada por credencial por produto e organização, criada só por CLI. Exige `Idempotency-Key`. Flag `PRODUCT_API_ENABLED`.
- **Revogação:** o token do produto dura 10 min, então revogar acesso não derruba a sessão na hora. Existe um evento assinado na fila, hoje só para o `diario-digital`. Flag `PRODUCT_EVENTS_ENABLED`.

## 5. Lacuna conhecida: espaço do cliente dentro do produto

Contratar um produto no Admin só grava uma linha no Core DB. O produto não é avisado [HOJE]. No Diário, uma organização nova é barrada no login até alguém criar a rede e a escola dela, à mão, no banco do Diário.

**[PLANEJADO] criar o espaço vazio ao contratar:**

1. O Admin grava o contrato e, na mesma operação, um pedido "criar espaço".
2. A Central o entrega ao produto por evento assinado, com retentativas (a fila de revogação já existe, mas hoje serve só ao Diário).
3. O produto cria o espaço vazio, idempotente, e devolve o identificador.
4. O Admin mostra o estado por produto: criado, pendente ou com erro.
5. Descontratar desativa o espaço; nunca apaga.

Faltam à Central a cidade e o estado da organização, que o Diário exige.

## 6. APM Digital hoje [HOJE]

- **Stack:** FastAPI + Postgres com RLS (`apps/api`), Next.js (`apps/web`), serviço de OCR (`apps/ocr`).
- **Tenancy:** organização → escola, com **uma escola por organização** (índice único). O tenant vem da membership da sessão, nunca de header, query ou corpo.
- **Auth própria:** tabelas `users`, `memberships`, `sessions` (cookie httpOnly, 30 min de inatividade, 12 h absolutas) e `invitations` (72 h). **Nenhuma referência à Central.**
- **Papéis em código** (ADR-016, 21 permissões): `school_admin`, `treasurer`, `staff`, `viewer`. As chaves já têm o formato aceito pela Central. Na tela os rótulos diferem das chaves (por exemplo, `staff` aparece como funcionário).
- **Entregue:** despesas, solicitações, OCR, fechamento mensal e relatórios, campanhas com produtos e carrinho, categoria "Vendas de campanha".
- **Pendente, o dono mandou esperar:** conciliação do extrato (S7 a S9).
- **Pix:** interface `PixProvider` com **apenas** o `SandboxPixProvider`. O provedor real (Banco do Brasil) não existe.
- **Conta Pix da escola:** tabela `payment_accounts`, uma ACTIVE por escola, com `secret_ref` (`env:NOME` ou `vault:caminho`). O banco nunca guarda credencial de provedor.
- **Webhook:** `POST /webhooks/pix/{provedor}` com `X-Webhook-Secret`. A API pergunta de novo ao provedor antes de acreditar na notificação.
- **Link público sem login:** `/escola/{slug}`, com o slug de `schools.slug` do APM (único global).

**Mapeamento APM → ecossistema [PLANEJADO]:** produto `apm-digital` no catálogo, `base_url` do APM e cargos `school_admin`, `treasurer`, `staff` e `viewer`. Administrador da empresa (papel na organização, na Central) e `school_admin` (cargo no produto) são conceitos distintos; em geral a mesma pessoa tem os dois.

## 7. Pagamentos: desenho planejado [PLANEJADO]

Este é o desenho do dono. Nada disto existe ainda.

- **Conta mestre:** a Forklin tem uma única chave de API no gateway, configurada no backend da Central. Cada escola é uma subconta (recebedor), sem chave individual.
- **Criação da subconta:** o Admin cadastra a organização com os dados bancários, a Central cria a subconta no gateway e guarda o `recebedor_id` atrelado à escola.
- **Split do Pix:** (1) o gateway retém a taxa do Pix; (2) a Forklin retém um valor fixo (ex.: R$ 0,50) para a conta mestre; (3) o saldo vai direto para o recebedor da escola.
- **Premissa:** o dinheiro da escola não passa por conta da Forklin; quem repassa é o gateway.

**Onde o desenho diverge da realidade ou ainda tem lacuna:**

- A Central **não tem** dados bancários, `recebedor_id` nem chave de gateway. Uma organização é nome, slug, contato e notas.
- **Gateway não escolhido [ABERTO].** Ele precisa ter subconta e split. Na pesquisa de 2026-10-14 (confirmar antes de implementar), a AbacatePay não documenta subconta nem split. Decisão do dono: só Pix no MVP.
- "Isenção de bitributação" **não foi verificada**. Confirmar com contador e gateway antes de afirmar.
- O APM já tem `payment_accounts` por escola; o desenho novo precisa dizer onde o `recebedor_id` mora (seção 11).
- O dashboard de faturamento do Admin não tem como receber dado do APM: `/overview` responde 501 e a API de produto só tem `users`. Como a Central não guarda dado de produto, é preciso definir um contrato de métricas **agregadas** que o produto reporta.

## 8. Link público e fluxo do pai

**[HOJE]**

1. O pai abre `/escola/{slug}` sem login. O APM resolve o slug e devolve nome, cores, valores sugeridos e quais campos de identificação a escola exige (obrigatório, opcional ou oculto).
2. Campanhas e identidade visual vêm da **API do APM**. A Central não repassa dado de produto.
3. O pai escolhe valor ou produtos da campanha, informa os dados mínimos e o APM cria a cobrança Pix.
4. O provedor avisa por webhook, e o APM reconfirma com o provedor antes de liquidar. **O frontend nunca decide que algo foi pago.**

**[PLANEJADO]**

- O slug passa a nascer na Central (`organizations.slug`, informado no Admin ou gerado do nome). O APM o recebe quando o espaço for criado, para os dois coincidirem. Hoje são slugs separados.
- Domínio público `doar.forklin.com/{slug}`: não há configuração dele em nenhum repositório.
- Tela inicial do pai com dois botões, "Contribuição Mensal" e "Campanhas" (`docs/thelastversion.md`). O significado de "Contribuição Mensal" está em aberto.
- Depois do pagamento, o APM avisa a Central de forma assíncrona para as métricas do Admin (ver o fim da seção 7).

## 9. Regras que não podem ser violadas

1. Autorização e isolamento entre organizações são sempre verificados no backend, nunca confiados ao frontend nem à URL.
2. Produto não lê o Core DB nem o banco de outro produto. A Central não guarda nem faz proxy de dado de produto.
3. O destino de um redirecionamento vem do banco (`products.base_url`), nunca de parâmetro da requisição.
4. Tokens nunca ficam em `localStorage`. A sessão fica em cookie `HttpOnly` no servidor.
5. Uma pessoa, uma organização. A organização nunca fica sem Administrador.
6. Tudo que não existe ou não é seu responde com o mesmo 404, sem permitir descobrir o que existe (lição de quatro vazamentos no schema financeiro do APM).
7. O banco do APM guarda só referência a segredo (`secret_ref`), nunca a credencial.
8. Só o webhook do provedor, reconfirmado, liquida um pagamento. O APM nunca move dinheiro.
9. Integração nova entra atrás de flag que se desliga sem novo deploy, com backup verificado e ensaio em cópia antes de tocar banco de produção.
10. Descontratar ou desativar nunca apaga dado.

## 10. O que falta fazer

**A. Independe da Central (pode começar assim que o dono aprovar a ordem).** Ordem proposta em 2026-10-14, ainda não aprovada:

1. Ajustes pequenos de `docs/thelastversion.md`: "Personalização" vira "Campanhas", sidebar sem "Despesas" duplicada, rótulo no lugar de "Saídas pagas" e gráficos com dados reais.
2. Campanhas v2: dashboard por campanha, lista de entregas e pagamentos, PDF. Custo por produto (`unit_cost_cents`) e entrega marcada só pela gestão.
3. Gateway Pix real, com split se a decisão 11.2 exigir.
4. Conciliação do extrato (S7 a S9) e Livro Caixa. A verba do PDDE exige mais de uma conta bancária por escola.
5. Prestação de contas do PDDE.
6. Fase 2 fiscal (retenções, guias, obrigações acessórias). Sem cálculo de imposto na Fase 1.

Rifas estão **fora do MVP**.

**B. Entrar no ecossistema (só depois da decisão 11.1):**

1. Cadastrar `apm-digital` no catálogo, com `base_url` e os quatro cargos.
2. Implementar `/sso/callback` no APM e validar o JWT pelo JWKS.
3. Mapear `users` e `memberships` do APM para `users` e `organization_users` da Central: id, e-mail, uma organização por pessoa.
4. Receber o pedido "criar espaço" (seção 5): criar organização e escola vazias com o slug e o id da Central.
5. Cadastro de pessoas pela Central (API de produto) e fim do login e dos convites próprios, ou convivência temporária.

**C. Split de pagamento (depende de 11.2):** a Central cria a subconta e guarda o `recebedor_id`; o APM cria a cobrança com a regra de split.

## 11. Decisões em aberto

| # | Pergunta | Padrão até o dono decidir |
| --- | --- | --- |
| 1 | O MVP do APM nasce dentro do ecossistema (SSO) ou lança com login próprio e integra depois? | Login próprio. Não implementar nada de SSO |
| 2 | Qual gateway (precisa de subconta e split) e onde mora o `recebedor_id`: Central (desenho do dono) ou `payment_accounts` do APM? | Sem gateway real. Sugestão: a Central cria a subconta e envia o `recebedor_id` ao APM, que guarda cópia, para o checkout não depender da Central estar no ar |
| 3 | Quem é o dono do slug: a Central (desenho) ou `schools.slug` do APM (hoje)? | O do APM, sem mudar |
| 4 | "Contribuição Mensal" é só o nome do fluxo avulso ou cobrança recorrente de verdade? | Fluxo avulso |
| 5 | Inadimplência no MVP | Meta e adesão |
| 6 | A contadora entra no sistema (papel `accountant`)? | Não |
| 7 | Um contador humano revisa antes de entregar ao governo? | Sem resposta |
| 8 | Em qual modo o Diário roda em produção (flag `FORKLIN_CORE_ENABLED`)? | Não verificado |

## 12. Fontes

- Central: `docs/adr/0002`, `0003`, `0004`, `0006`, `0011` e `docs/spec/ROTAS_ACESSO_ADMIN.md`, em `../../api` (versão `origin/integracao`).
- Diário: `ARCHITECTURE.md`, `src/lib/forklin-sso.ts` e `src/lib/forklin-provisionar.ts`, em `../DiarioDigital`.
- APM neste repositório: `docs/tenancy.md`, `docs/auth.md`, `docs/financial-model.md`, `docs/public-flow.md`, `docs/campaigns.md` e `docs/thelastversion.md`.
