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

### 3. O perímetro privilegiado: duas funções `SECURITY DEFINER` e o que elas precisam
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

### 9. Revogação e limites conhecidos
- Suspender na Central vale **no próximo login** (a sessão local dura o que já dura). A Secretaria também suspende na tela de equipe (revoga as sessões na hora). Receptor de eventos de revogação: fase 3.
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
2FA (decidido no ADR-016 para antes de produção com dinheiro real), receptor de eventos de revogação (fase 3), desligar a senha local, importar usuários antigos em lote.

## Como verificar
`tests/test_forklin_sso.py` (39 testes, com tokens EdDSA reais e a rede simulada: caminho feliz, retorno da mesma pessoa, vínculo por e-mail, conflito, suspensa, cargo, audiência/emissor/validade/assinatura/`none`, `state`, sessão trazida pelo navegador, nada pessoal no log, aviso idempotente, endereços diferentes para nomes iguais, avisos inválidos, `apm_app` sem inserção direta); as listas fechadas de segurança (`test_app_role`, `test_auth_rls`, `test_posture`, `test_migrations`, `test_createrole_admin`, `financial/*`) aprenderam as peças novas; no site, `src/lib/forklin.test.ts`.

## Rollback
`FORKLIN_CORE_ENABLED=false` e reiniciar: o botão some e as rotas voltam a 404; quem entrou pela Central e não tem senha local usa "esqueci a senha". A migração 0023 acrescenta duas colunas nulas, as duas funções, as políticas e os privilégios acima; o `downgrade` os remove (testado). **Irreversível:** escolas e usuários criados a partir da Central (dá para suspender, não "des-criar").
