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

### 3. O perímetro privilegiado: duas funções `SECURITY DEFINER` e o que elas precisam (a terceira, da revogação, está na seção 9)
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

### 7. Convivência com a senha local
- `FORKLIN_CORE_ENABLED=false` (padrão): tudo como hoje; o botão **não aparece**; `/sso/*` e `/forklin/events` respondem 404.
- `true`: o botão aparece e o SSO vale. **O login por senha continua** para quem tem senha. Quem entrou só pela Central não tem senha local ("esqueci a senha" não faz nada por essa conta, com a resposta igual de sempre). Desligar a senha local é decisão posterior do dono do produto.
- A flag só deixa a API subir com `API_CENTRAL_URL`, `FORKLIN_APP_URL` e `FORKLIN_PRODUCT_SECRET` (e `https` em produção).

### 8. Funcionários pela Central (fase 2, não feita)
Hoje a Secretaria cria funcionário em `/painel/equipe` (`/api/v1/employees`; ponto único `app/auth/invite.py`). Com a Central ligada, esse ponto chamaria `POST /product-api/v1/users` (`Idempotency-Key`, `role_key`) e só gravaria local depois do 201/200 da Central; suspender/reativar chamaria `PATCH`. **Bloqueio:** ver o item 1 abaixo.

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
- **Limites conhecidos.** (1) A pessoa é desconectada; a entrada de volta é **só pela Central**. O **login por senha continua existindo** até a etapa separada que o desliga para quem tem vínculo com a Central: ela **não** foi feita, e a tela `/painel/equipe` e as de funcionário seguem como estão (etapa posterior). Enquanto isso, quem tem senha local pode entrar por ela mesmo depois de revogada na Central. (2) O evento age sobre as sessões abertas **no instante em que chega**: uma sessão criada logo depois (por exemplo por senha) não é afetada, e um evento antigo reapresentado dentro dos 2 minutos de validade desconecta a pessoa de novo. (3) Uma sessão é cortada na próxima requisição dela, não no meio de uma resposta. (4) A Secretaria também suspende na tela de equipe: aí a sessão cai na próxima requisição da pessoa (`membership_inactive`), sem evento.
- O `/sso/callback` **não tem limite de tentativas próprio** (o código é de uso único, 256 bits e 60 s, e a Central limita os pedidos de código por pessoa). Se a revisão de segurança pedir, entra o limite por endereço.
- O `/sso/callback` **não tem limite de tentativas próprio** (o código é de uso único, 256 bits e 60 s, e a Central limita os pedidos de código por pessoa). Se a revisão de segurança pedir, entra o limite por endereço.

## O que falta para produção (a Forklin precisa responder)
1. **Várias escolas por produto.** O ADR 0011 da Central diz que cada instalação pertence a **uma organização** e que a credencial do produto é **por (produto, organização)**; "vários tenants por organização×produto" está adiado. O APM é **uma instalação para muitas escolas**. A **entrada (SSO)** funciona com uma credencial **sem organização**; o **cadastro de funcionários pela Central** (`/product-api/v1`, que exige credencial com organização, `credential_org_required`) não. Preciso de uma saída: (a) a credencial sem organização valer também na API de produto, com a organização no corpo; (b) uma credencial por escola; (c) a Central aceitar organização = escola de outro modo.
2. **Cadastro do APM em "Novo sistema":** Nome `APM Digital`, Slug `apm-digital` (é o `aud`), URL base = **domínio público do APM**, Descrição, e os cargos `secretaria` e `funcionario`. Mais o **destino de eventos** do produto (`set-product-events-url`; o Admin ainda não tem o campo).
3. **No servidor do App:** acrescentar `"apm-digital": "https://<dominio-do-apm>/login"` em `PRODUCT_LOGIN_URLS`. É para onde o App devolve quem tem sessão no App mas **não tem acesso ao APM** (o APM mostra "sem acesso, fale com a secretaria"; a pessoa não é levada ao App). Sem a entrada, o App mostra um aviso genérico na própria Visão Geral.
4. **URL da API Central**, o **segredo do produto** (só no ambiente, nunca no chat) e o JWKS acessível do servidor do APM.
5. Decidir se **a mudança na Central** (migração 0012, fila generalizada, aviso na contratação, claim `org_name`, os dois comandos) entra no repositório `api` dela.
6. Rodar `resend-product-notices` uma vez, para as organizações que já contrataram o produto antes do aviso existir.
7. Decidir se **cada escola é uma organização** (a regra do APM é uma escola por conta: a resposta natural é sim).
8. **Revisão de segurança independente** do fluxo de login antes de ligar com dinheiro real.

## Fora do escopo
2FA (decidido no ADR-016 para antes de produção com dinheiro real), desligar a senha local para quem tem vínculo com a Central (etapa posterior, com a tela de equipe), importar usuários antigos em lote. O receptor de eventos de revogação **está feito** (seção 9).

## Como verificar
`tests/test_forklin_sso.py` (39 testes, com tokens EdDSA reais e a rede simulada: caminho feliz, retorno da mesma pessoa, vínculo por e-mail, conflito, suspensa, cargo, audiência/emissor/validade/assinatura/`none`, `state`, sessão trazida pelo navegador, nada pessoal no log, aviso idempotente, endereços diferentes para nomes iguais, avisos inválidos, `apm_app` sem inserção direta); `tests/test_forklin_revocation.py` (25 testes: cada evento de revogação encerra as sessões da pessoa e de mais ninguém sem tocar em matrícula, situação e senha; a pessoa entra de novo pela Central; repetição, pessoa desconhecida e organização trocada respondem 200 igual a um acerto; evento ignorado; 400 sem `user_id`; assinatura, `aud`, `iss`, validade, `alg=none` recusados; flag desligada 404; política do `apm_definer` e o `apm_app` sem alcance sobre sessões alheias); as listas fechadas de segurança (`test_app_role`, `test_auth_rls`, `test_posture`, `test_migrations`, `test_createrole_admin`, `financial/*`) aprenderam as peças novas; no site, `src/lib/forklin.test.ts`.

## Rollback
`FORKLIN_CORE_ENABLED=false` e reiniciar: o botão some e as rotas voltam a 404; quem entrou pela Central e não tem senha local usa "esqueci a senha". A migração 0023 acrescenta duas colunas nulas, as duas funções, as políticas e os privilégios acima; a 0025 acrescenta a função de revogação, as duas políticas e as duas concessões em `sessions` e o motivo `central_revoked`; o `downgrade` de cada uma os remove (testado). **Irreversível:** escolas e usuários criados a partir da Central (dá para suspender, não "des-criar").
