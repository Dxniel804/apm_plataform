# ADR: entrada pela Central Forklin (SSO) e ambiente vazio quando a organização contrata o produto (2026-10-15)

**Status:** IMPLEMENTADO e testado **só no ambiente local** (APM + uma cópia local da Central). Nada liga em produção até a lista de "O que falta para produção" ser resolvida. Estende o ADR-016 (identidade) e o ADR-020 (uma escola por conta). Plano de origem: [forklin-employees.md](forklin-employees.md). Contrato da Central: `api/docs/adr/0011-contrato-central-produto-v1.md` e `0003-authentication-and-sso.md` (branch `origin/integracao`). A mudança correspondente na Central **ainda não está no repositório dela**: está numa cópia local, à espera da decisão do dono do produto (seção "Mudança na Central").

## Contexto
Hoje o APM tem login próprio (e-mail e senha, sessão em cookie HttpOnly, convites). A Forklin quer **uma identidade só, na Central**: a pessoa abre o App, vê o "APM Digital" e clica em **Acessar**; ou clica em **ENTRAR COM FORKLIN** na tela de login do APM. O Diário Digital já faz isso (`forklin-sso.ts`, `/sso/start`, `/sso/callback`, `forklin-provisionar.ts`); este ADR repete o modelo no APM, que é Python/FastAPI. Há uma segunda necessidade, que o Diário **não** atende: quando alguém cria uma organização e atrela o produto a ela, o **ambiente vazio** deve nascer sozinho (no Diário isso é um script manual, `forklin-link-org.ts`).

## Decisão

### 1. Fluxo de entrada
1. **Do App:** Acessar → a Central cria um código de uso único (60 s) → o navegador vai a `{URL base}/sso/callback?code=…`.
2. **Do APM:** o botão **ENTRAR COM FORKLIN** abre `/sso/start`, que gera um `state` (256 bits), guarda em cookie HttpOnly de 10 min e manda o navegador a `{FORKLIN_APP_URL}/entrar?produto=apm-digital&state=…`. O App devolve o mesmo `state` junto do código.
3. **`/sso/callback`:** confere o `state` quando o cookie existe (fluxo iniciado no App não tem `state`: risco aceito, igual ao Diário; o código é de uso único e vive 60 s), troca o código na Central (`POST /launch-codes/exchange-product` com `Authorization: Bearer <segredo do produto>`, 5 s), verifica o JWT (**só EdDSA**, JWKS da Central em cache de 5 min, `iss=forklin`, `aud=apm-digital`, `exp`, `iat`; `none` e HS256 recusados) e cria a **sessão local do mesmo jeito do login por senha** (mesmo cookie, mesmo CSRF, mesma tabela `sessions`; uma sessão que o navegador já trazia é encerrada, nunca adotada). Depois vai a `/painel`.
4. **Toda falha** volta a `/login?erro=<palavra>` (`org`, `acesso`, `cargo`, `conflito`, `expirado`, `indisponivel`), com frase em português; o motivo vai só ao log, **sem e-mail, nome, token ou segredo**.

**Os três casos do botão ENTRAR COM FORKLIN** (é o `/entrar` do App, o mesmo do Diário): **com sessão no App e com acesso** entra direto, sem pedir senha; **com sessão e sem acesso ao APM** volta ao login do APM com `?erro=acesso` (frase "sem acesso", sem ir ao App); **sem sessão** vai ao login do App e segue ao APM depois de entrar. Quem entra pelo **App** (login direto em `localhost:3100`) cai na Visão Geral, com os produtos, e o **Acessar** do produto leva ao APM sem login.

Onde mora: as rotas são da API (`/api/v1/forklin/sso/start|callback`, `GET`) e o site as expõe como `/sso/start` e `/sso/callback` por dois route handlers do Next que só repassam (cookies, query, `Location` e `Set-Cookie`), sem seguir o redirecionamento. Em produção, `FORKLIN_APP_URL` tem de ser `https`; `API_CENTRAL_URL` é `https` ou o nome interno do serviço na rede do deploy (`http://api-central:8000`, como o App faz): só o servidor a chama.

### 2. Dados novos (migração 0023)
`users.central_user_id uuid UNIQUE NULL` e `organizations.central_org_id uuid UNIQUE NULL` (a organização do APM **é** a conta de uma escola: ADR-020). As duas são opcionais: nada muda para quem nunca veio da Central. No ORM as duas são `deferred` (o papel da aplicação não as lê).

### 3. O perímetro privilegiado: duas funções `SECURITY DEFINER` e o que elas precisam (a terceira, da revogação, está na seção 9; a quarta, só de leitura, `is_central_linked`, na seção 7)
Antes de existir sessão não há contexto de escola e a RLS é forçada: o mesmo problema do login e da recuperação de senha. A lista fechada do ADR-016 cresce por **duas funções**:
- **`provision_forklin_school(central_org_id, name, slug)`**: cria a conta vazia (organização + a única escola; os gatilhos já existentes criam as configurações e as 12 categorias padrão). **Idempotente**: achar a organização devolve a escola e não muda nada; se o endereço (`slug`) estiver ocupado, acrescenta 4 caracteres; corrida entre dois pedidos é tratada.
- **`sso_sign_in(central_user_id, central_org_id, email, full_name, role)`**: acha a pessoa pelo id da Central; senão **vincula por e-mail** a uma conta local **sem vínculo** (e só ativa); senão cria a pessoa **sem senha**; garante a matrícula com o cargo que a Central mandou (a Central manda no cargo; uma matrícula **suspensa** localmente continua recusada). Nunca mescla: e-mail já ligado a outra pessoa da Central é `conflict`. Devolve `ok`, `org_unknown`, `conflict`, `inactive`, `suspended` ou `invalid`.

Como os gatilhos de uma escola nova (configurações, categorias, auditoria) rodam com o papel de quem chamou, o `apm_definer` ganhou, **limitados por política a organizações que têm `central_org_id`**: INSERT em `organizations`, `schools`, `school_settings`, `categories` e `audit_logs` (por coluna), mais UPDATE de `users.central_user_id` (só de quem ainda não tem vínculo) e de `memberships.role` (só de linha ativa). O `apm_app` só ganhou EXECUTE nas duas funções; uma tentativa dele de inserir direto numa dessas tabelas continua recusada (teste). A checagem de postura que roda ao subir a API conhece as 7 políticas e as 2 funções novas.

### 4. Cargos
Tabela fixa: `secretaria` → `secretaria`, `funcionario` → `staff`. **Cargo desconhecido é recusado** (`cargo`), nunca vira padrão. Uma **escola nova só nasce para uma `secretaria`**: um funcionário que chega antes de a escola existir é recusado (`org`).

### 5. Ambiente vazio quando a organização contrata (o aviso)
- **Receptor no APM:** `POST /api/v1/forklin/events` (servidor a servidor, sem Origin e sem sessão; isento da checagem de Origin, e só por isso). O **token assinado da Central é a autenticação**: EdDSA, `aud=apm-digital`, `iss=forklin`, `event=organization.product_contracted`, `organization_id` UUID, validade de **no máximo 2 minutos**. Efeito **idempotente**: a conta vazia é criada uma vez; repetir ou reapresentar o aviso acha a conta e nada muda (por isso não há tabela de `jti`). Nome da escola = `organization_name` do aviso (ou "Minha escola").
- **Reserva no primeiro acesso:** se o aviso não chegou, a primeira `secretaria` que entra faz a mesma conta vazia (a mesma função). O nome vem da claim opcional `org_name` do token, que a cópia local da Central passou a mandar.

### 6. Mudança na Central (feita só numa cópia local; o dono do produto decide se vai ao repositório `api`)
- **Migração 0012:** `products.events_url` (destino dos eventos *daquele* produto; hoje era uma variável de ambiente única, só do Diário) e `product_events.user_id` passa a aceitar vazio (o evento é da organização).
- **Fila generalizada** (`services/product_events.py`): o destino é o do produto (`events_url`) ou, só para o Diário, o da variável antiga; o Diário e a revogação de acesso seguem como estavam (teste existente passa).
- **Gatilho:** `add_contract` grava o aviso na **mesma transação** do contrato (só com `PRODUCT_EVENTS_ENABLED` ligado e o produto com `events_url`).
- **Claim `org_name`** (opcional, aditiva) no token de acesso do produto.
- **Comandos do operador:** `set-product-events-url --product … --url …|--clear` e `resend-product-notices --product …` (reenvia o aviso às organizações ativas que já contrataram o produto, para as de antes da mudança).
- 5 testes novos na Central; a suíte dela (818) passa.

### 7. Convivência com a senha local (decisão do dono do produto, etapa 4)
As pessoas são cadastradas **só na Central** (ADR 0014 da Central: `docs/adr/0014-acesso-por-produto-contrato-de-integracao.md` no repositório `api` dela). O administrador da organização concede os papéis `secretaria` e `funcionario`, e a pessoa entra **somente pela Central**: pelo botão "Entrar com Forklin" do APM (quem abre o APM direto) ou pelo App. Quem vem da Central **não tem segundo caminho de entrada**. Nada é apagado: contas, tabelas de sessão e dados ficam; só saem a oferta de cadastrar/convidar equipe e a senha local de quem tem vínculo com a Central.

Tudo atrás da chave `FORKLIN_CORE_ENABLED` (padrão `false`):

| | `false` (padrão) | `true` |
|---|---|---|
| Tela de login | e-mail e senha, "esqueci minha senha", aviso do convite; sem o botão | **só o botão "Entrar com Forklin"** (e "Contribuir", das famílias); sem formulário, sem "esqueci", sem aviso de convite |
| `/sso/*` e `/forklin/events` | 404 | valem |
| Login por senha de quem **tem** `central_user_id` | entra, como sempre | **recusado** com a resposta, o código (`invalid_credentials`), o trabalho (uma verificação do hash de mentira) e a contagem de tentativas de uma senha errada; nenhuma pista de que a conta existe |
| Login por senha de quem **não tem** vínculo (demo, legado, emergência) | entra | entra, como hoje |
| "Esqueci a senha" (`/auth/password-reset/request`) para quem tem vínculo | cria o link e manda o e-mail | **202 igual ao de sempre, nada enviado, nada criado** (igual a um e-mail desconhecido) |
| Redefinir com um link (`/auth/password-reset/confirm`) de quem tem vínculo (link feito antes do vínculo) | troca a senha | **400 `reset_invalid`** (como qualquer link que não vale); senha, sessões e e-mails intactos |
| Trocar a senha logado (`/auth/password`) de quem tem vínculo | troca | 403 `current_password_incorrect` (a pessoa não tem senha local para trocar) |
| `/api/v1/employees...` (listar, criar, reenviar, cancelar convite, suspender, reativar) e `POST /api/v1/invitations` | funcionam | **404** (`not_found`), até para quem não tem sessão |
| `POST /api/v1/invitations/accept` (convite enviado antes da virada) | aceita | **400 `invitation_invalid`**, igual a um convite vencido: ninguém se cadastra localmente |
| Menu e tela **Equipe** (`/painel/equipe`) | para quem tem `invitations:create` | **somem**; abrir o endereço volta à área da pessoa |

Como a API sabe quem tem vínculo: antes de haver sessão o papel da aplicação não lê `users.central_user_id` (a RLS é forçada e não há contexto de escola), então a **migração 0026** acrescenta uma função `SECURITY DEFINER` **só de leitura**, `is_central_linked(user_id, email)`, com EXECUTE só para o `apm_app` e nenhuma permissão nova de tabela, coluna ou política. Com a chave desligada ela nem é chamada. O site lê a chave só no servidor: tira `invitations:create` da sessão que entrega ao painel (esconder; quem confere de verdade é a API).

A chave só deixa a API subir com `API_CENTRAL_URL`, `FORKLIN_APP_URL` e `FORKLIN_PRODUCT_SECRET` (e `https` em produção).

**O que a etapa 4 não faz, de propósito.** Uma pessoa sem vínculo (conta antiga) continua entrando por senha; ao entrar pela Central pela primeira vez ela é **vinculada por e-mail** e dali em diante a senha deixa de valer. O hash dela fica na linha (nada é apagado). A lista de pessoas já existentes continua no banco; só a tela de cadastro saiu. A API de leitura da equipe (`GET /employees`) também saiu: a web não a usa em outro lugar.

### 8. Funcionários pela Central (fase 2: DESCARTADA)
A ideia anterior era o APM chamar `POST /product-api/v1/users` da Central quando a Secretaria cadastrasse alguém. **Foi descartada** (etapa 4): quem cria as pessoas é a Central (painel administrativo, ADR 0014 dela), e o APM **nunca cadastra equipe**. A API de produto da Central **não é necessária** para equipe; o APM só usa a credencial para trocar o código de entrada (`/launch-codes/exchange-product`) e para a chave pública (JWKS). O ponto único `app/auth/invite.py` e as rotas de convite continuam no código (nada foi apagado), mas ficam fechadas com a chave ligada (seção 7). O cargo (`secretaria`/`funcionario`) vem da Central a cada entrada; mudar cargo ou tirar acesso é feito lá, e o aviso da seção 9 derruba as sessões.

### 9. Revogação: a Central encerra as sessões na hora (migração 0025)
Regra da Central: quando o acesso de uma pessoa ao produto é retirado ou suspenso, a pessoa é desativada, o cargo muda, ou a organização ou o produto é desligado, a Central manda ao produto um evento assinado e o produto **encerra as sessões abertas dessa pessoa imediatamente**. O receptor é o mesmo `POST /api/v1/forklin/events` da seção 5 (servidor a servidor, sem sessão e sem Origin; o token EdDSA assinado, `aud=apm-digital`, `iss=forklin`, validade de até 2 minutos, **é** a autenticação). Corpo `{"token": "<jwt>"}`; claims: `iss`, `aud`, `iat`, `exp`, `jti`, `event`, `organization_id` (UUID da organização na Central) e, nos eventos abaixo, `user_id` (UUID da pessoa na Central).

**Lista de eventos (lista permitida; o que não está nela é ignorado):**

| Evento | Efeito no APM |
|---|---|
| `organization.product_contracted` | Cria a conta vazia (seção 5). Sem mudança. |
| `access.revoked`, `access.suspended`, `user.disabled`, `access.role_changed`, `organization.suspended`, `organization.inactive`, `product.inactive` | Encerra **todas** as sessões abertas dessa pessoa (`revoked_reason = 'central_revoked'`). Responde 200 `{"status":"processed"}`. |
| qualquer outro nome | 200 `{"status":"ignored"}`; só o **nome** do evento vai ao log. Nada acontece. |

`organization.suspended` e `organization.inactive` são os dois estados que não são `active` do enum `OrganizationStatus` da Central; um estado novo lá precisa entrar em `REVOKING_EVENTS` (`app/forklin/central.py`). O evento de uma organização vale para a pessoa que ele nomeia (`user_id`), como os demais.

**Comportamento.**
- A função `SECURITY DEFINER` `revoke_forklin_sessions(central_user_id, central_org_id)` (a terceira do perímetro; sem sessão não há contexto e a RLS é forçada) acha a pessoa por `users.central_user_id`, **confere que ela tem matrícula ativa na organização cujo `central_org_id` é o do evento** (defesa em profundidade) e revoga as sessões abertas dela. **Pessoa desconhecida ou de outra organização é um não-fazer-nada que responde 200 com o mesmo corpo de um acerto**: nada é revelado a quem enviar o evento. Repetir o evento é inofensivo (idempotente; não há tabela de `jti`, a validade de 2 minutos limita a reapresentação).
- **Não** muda matrícula, situação do usuário nem senha: se a Central devolver o acesso, a pessoa simplesmente entra de novo pela Central.
- `user_id` ausente ou inválido num evento que o exige (ou `organization_id` inválido) responde **400** `invalid_event` (a assinatura estava certa, faltam dados); assinatura, `aud`, `iss`, validade, `alg=none` e afins respondem **401**, como antes. `FORKLIN_CORE_ENABLED=false` mantém 404.
- **Privilégios novos:** EXECUTE da função só para `apm_app`; para `apm_definer`, `SELECT (user_id, revoked_at)` e `UPDATE (revoked_at, revoked_reason)` em `sessions` e duas políticas (`sessions_definer_select`, `sessions_definer_update`) que só mostram e só mudam sessões de quem tem `central_user_id`; o UPDATE só leva uma sessão aberta a revogada com o motivo `central_revoked`. O `apm_app` **não** ganhou nada sobre `sessions` (continua só nas próprias).
- **Limites conhecidos.** (1) A pessoa é desconectada; a entrada de volta é **só pela Central**. Com `FORKLIN_CORE_ENABLED=true` o login por senha **não existe** para quem tem vínculo com a Central (seção 7), então uma revogação na Central não pode ser contornada por uma senha antiga. Quem não tem vínculo (conta de demonstração ou legada) segue com a senha e **não** recebe esses eventos. (2) O evento age sobre as sessões abertas **no instante em que chega**: uma sessão criada logo depois (por exemplo por senha) não é afetada, e um evento antigo reapresentado dentro dos 2 minutos de validade desconecta a pessoa de novo. (3) Uma sessão é cortada na próxima requisição dela, não no meio de uma resposta. (4) Com a chave ligada a tela de equipe não existe; a suspensão local de uma matrícula (que a Central pode ter ignorado) segue recusada pela API (`membership_inactive`), mas a decisão é da Central.
- O `/sso/callback` **não tem limite de tentativas próprio** (o código é de uso único, 256 bits e 60 s, e a Central limita os pedidos de código por pessoa). Se a revisão de segurança pedir, entra o limite por endereço.

## O que falta para produção (a Forklin precisa responder)
1. ~~**Várias escolas por produto.**~~ **Não bloqueia mais nada para a equipe.** O ADR 0011 da Central diz que a credencial da API de produto (`/product-api/v1`, que exige credencial com organização) é por (produto, organização) e que "vários tenants por organização×produto" está adiado, mas o APM **não cadastra mais equipe** (seção 8): só precisa da **entrada (SSO)**, que funciona com uma credencial **do produto sem organização** (a troca de código e o JWKS não pedem organização). Fica só uma confirmação: que a Central emita essa credencial sem organização para o `apm-digital`.
2. **Cadastro do APM em "Novo sistema":** Nome `APM Digital`, Slug `apm-digital` (é o `aud`), URL base = **domínio público do APM**, Descrição, e os cargos `secretaria` e `funcionario`. Mais o **destino de eventos** do produto (`set-product-events-url`; o Admin ainda não tem o campo). Este destino é o que derruba as sessões (seção 9): sem ele a revogação não chega.
3. **No servidor do App:** acrescentar `"apm-digital": "https://<dominio-do-apm>/login"` em `PRODUCT_LOGIN_URLS`. É para onde o App devolve quem tem sessão no App mas **não tem acesso ao APM** (o APM mostra "sem acesso, fale com a secretaria"; a pessoa não é levada ao App). Sem a entrada, o App mostra um aviso genérico na própria Visão Geral.
4. **URL da API Central**, o **segredo do produto** (só no ambiente, nunca no chat) e o JWKS acessível do servidor do APM.
5. Decidir se **a mudança na Central** (migração 0012, fila generalizada, aviso na contratação, claim `org_name`, os dois comandos) entra no repositório `api` dela. O contrato de integração do ADR 0014 dela (sem cadastro de funcionário, botão "Entrar com Forklin", papel desconhecido recusado, revogação encerra as sessões) está cumprido pelo APM com a chave ligada.
6. Rodar `resend-product-notices` uma vez, para as organizações que já contrataram o produto antes do aviso existir.
7. Decidir se **cada escola é uma organização** (a regra do APM é uma escola por conta: a resposta natural é sim).
8. **Antes de ligar a chave em produção:** as pessoas que hoje entram por senha precisam existir na Central (com e-mail igual ao local, para o vínculo por e-mail) e ter o papel concedido; senão elas deixam de entrar (a tela de login deixa de oferecer a senha). Conferir uma conta de emergência **sem** vínculo para o suporte.
9. **Revisão de segurança independente** do fluxo de login antes de ligar com dinheiro real.

## Fora do escopo
2FA (decidido no ADR-016 para antes de produção com dinheiro real), importar usuários antigos em lote para a Central. Desligar a senha local de quem tem vínculo e fechar o cadastro de equipe **estão feitos** (seção 7). O receptor de eventos de revogação **está feito** (seção 9).

## Como verificar
`tests/test_forklin_sso.py` (39 testes, com tokens EdDSA reais e a rede simulada: caminho feliz, retorno da mesma pessoa, vínculo por e-mail, conflito, suspensa, cargo, audiência/emissor/validade/assinatura/`none`, `state`, sessão trazida pelo navegador, nada pessoal no log, aviso idempotente, endereços diferentes para nomes iguais, avisos inválidos, `apm_app` sem inserção direta); `tests/test_forklin_revocation.py` (25 testes: cada evento de revogação encerra as sessões da pessoa e de mais ninguém sem tocar em matrícula, situação e senha; a pessoa entra de novo pela Central; repetição, pessoa desconhecida e organização trocada respondem 200 igual a um acerto; evento ignorado; 400 sem `user_id`; assinatura, `aud`, `iss`, validade, `alg=none` recusados; flag desligada 404; política do `apm_definer` e o `apm_app` sem alcance sobre sessões alheias); `tests/test_forklin_central_only.py` (16 testes da etapa 4: rotas de equipe e de convite em 404 com a chave ligada e intactas desligada, convite antigo recusado, login por senha de quem tem vínculo recusado com a mesma resposta e o mesmo trabalho de uma senha errada, quem não tem vínculo segue entrando, "esqueci" e redefinição neutros, a função `is_central_linked`); as listas fechadas de segurança (`test_app_role`, `test_auth_rls`, `test_posture`, `test_migrations`, `test_createrole_admin`, `financial/*`) aprenderam as peças novas; no site, `src/lib/forklin.test.ts`, `src/app/login/page.test.tsx` e `src/components/painel/PainelPage.test.tsx` (login só com o botão e menu sem Equipe, ligado; como sempre, desligado).

## Rollback
`FORKLIN_CORE_ENABLED=false` e reiniciar: o botão some e as rotas voltam a 404; quem entrou pela Central e não tem senha local usa "esqueci a senha" (com a chave desligada o recuperar volta a valer para todos). A migração 0023 acrescenta duas colunas nulas, as duas funções, as políticas e os privilégios acima; a 0025 acrescenta a função de revogação, as duas políticas e as duas concessões em `sessions` e o motivo `central_revoked`; a 0026 acrescenta só a função de leitura `is_central_linked`; o `downgrade` de cada uma os remove (testado). **Irreversível:** escolas e usuários criados a partir da Central (dá para suspender, não "des-criar").
