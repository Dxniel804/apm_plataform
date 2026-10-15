# ADR: entrada pela Central Forklin (SSO) e cadastro de funcionários pela Central (2026-10-15)

**Status:** PROPOSTO. O dono do produto autorizou escrever e desenvolver localmente em 15/10/2026; **nada liga em produção** até a lista da seção "O que falta para produção" ser resolvida. Estende o ADR-016 (identidade) e o ADR-020 (uma escola por conta). Plano de origem: [forklin-employees.md](forklin-employees.md). Contrato da Central: `api/docs/adr/0011-contrato-central-produto-v1.md` e `0003-authentication-and-sso.md` (branch `origin/integracao`).

## Contexto
Hoje o APM tem login próprio (e-mail e senha, sessão em cookie HttpOnly, convites). A Forklin quer **uma identidade só, na Central**: a pessoa abre o App, vê o "APM Digital" e clica em **Acessar**; ou clica em **ENTRAR COM FORKLIN** na tela de login do APM. O Diário Digital já faz isso (`forklin-sso.ts`, `/sso/start`, `/sso/callback`, `forklin-provisionar.ts`); este ADR repete o modelo no APM, que é Python/FastAPI.

## Decisão

### 1. Fluxo
1. **Do App:** Acessar → Central cria um código de uso único (60 s) → navegador vai a `{URL base}/sso/callback?code=…`.
2. **Do APM:** o botão **ENTRAR COM FORKLIN** abre `/sso/start`, que gera um `state` (256 bits), guarda em cookie HttpOnly de 10 min e manda o navegador a `{FORKLIN_APP_URL}/entrar?produto=apm-digital&state=…`. O App devolve o mesmo `state` junto do código.
3. **`/sso/callback`** (rota da API, exposta na mesma origem pelo proxy do site, como `/api/*`): confere o `state` quando o cookie existe (fluxo iniciado no App não tem `state`: risco aceito e igual ao do Diário), troca o código na Central (`POST /launch-codes/exchange-product`, com `Authorization: Bearer <segredo do produto>`, 5 s), verifica o JWT (EdDSA, JWKS da Central em cache, `iss=forklin`, `aud=apm-digital`, `exp`, `jti`), provisiona e cria a **sessão local do mesmo jeito do login por senha** (mesmo cookie, mesmo CSRF, mesma tabela `sessions`). Depois redireciona a `/painel`.
4. **Toda falha** volta a `/login?erro=<código>` (`org`, `acesso`, `cargo`, `conflito`, `expirado`, `indisponivel`), com frase em português, sem revelar o motivo exato, e **nunca grava e-mail, nome, token ou segredo no log**.

### 2. Provisionar no primeiro acesso (uma função privilegiada, estreita)
Antes de existir sessão não há contexto de escola e a RLS é forçada: o mesmo problema do login e da recuperação de senha. Então **uma função `SECURITY DEFINER`** nova, `provision_sso_user(central_user_id, central_org_id, email, name, role_key)`, entra na lista fechada do ADR-016 e faz tudo numa transação:
- acha a escola pela **organização da Central** (`schools.central_org_id`, único). Escola desconhecida: ver a seção "Escola nova" abaixo;
- **traduz o cargo** por tabela fixa: `secretaria` → `secretaria`, `funcionario` → `staff`. **Cargo desconhecido é recusado** (`cargo`), nunca vira um padrão;
- acha o usuário por `users.central_user_id`; se não houver, **vincula por e-mail** (sem diferenciar maiúsculas) a um usuário local que ainda **não tenha vínculo**; se o e-mail já está ligado a outra pessoa da Central, recusa (`conflito`). Sem usuário nenhum, cria um **ativo, sem senha local**, com o mesmo id da Central;
- garante a matrícula na escola com o cargo traduzido (cria ou atualiza) e **respeita suspensão local**: matrícula suspensa na escola continua recusada.
A função só devolve `user_id` e `school_id`. O `apm_app` não ganha acesso a nenhuma tabela nova.

### 3. Dados novos (migração 0023)
`users.central_user_id uuid UNIQUE NULL`; `schools.central_org_id uuid UNIQUE NULL`. Nada é apagado, nenhuma coluna financeira muda.

### 4. Convivência com a senha local
- `FORKLIN_CORE_ENABLED=false` (padrão): tudo como hoje; o botão **não aparece**; `/sso/*` responde 404.
- `true`: o botão aparece e o SSO vale. **O login por senha continua funcionando** para quem já tem senha (a transição não tranca ninguém); quem entrou só pela Central não tem senha local, então "esqueci a senha" não faz nada para essa conta (resposta igual, como já é). Desligar a senha local de vez é uma decisão **posterior** do dono do produto.
- A flag **deixa de recusar a subida** só quando estão presentes `API_CENTRAL_URL`, `FORKLIN_APP_URL`, `FORKLIN_PRODUCT_SECRET` (e `https` fora de desenvolvimento). Sem eles continua recusando.

### 5. Funcionários pela Central (fase 2)
Hoje a Secretaria cria funcionário em `/painel/equipe` (rotas `/api/v1/employees`), e o ponto único é `app/auth/invite.py`. Com a Central ligada, esse ponto passa a chamar `POST /product-api/v1/users` (`Idempotency-Key` obrigatório, `role_key` `secretaria`/`funcionario`, timeout curto) e **só grava local depois que a Central confirma** (201 ou 200); suspender/reativar chama `PATCH /users/{id}` e só depois muda o local. Erros da Central (`seat_limit`, `email_in_other_org`, `org_inactive`, `role_unknown`) viram frases na tela. As rotas e a tela não mudam.

### 6. Revogação
A Central só emite eventos de revogação para o Diário (flag `PRODUCT_EVENTS_ENABLED`). Para o APM, **suspender na Central vale no próximo login**; a sessão local dura o que já dura hoje. Mitigação nesta fase: a Secretaria também pode suspender o funcionário na tela de equipe (revoga as sessões na hora). Quando a Central passar a avisar o APM, entra um receptor de eventos (`/api/v1/forklin/events`, assinado, `jti` guardado) em fase 3.

### 7. Teste local sem a Central
Uma **Central falsa** (`apps/api/tests/forklin_fake.py` e um modo de desenvolvimento) com chave EdDSA própria, `/.well-known/jwks.json`, `/launch-codes/exchange-product` e `/product-api/v1/users`, para os testes e para ver o fluxo no navegador. Cobrir: caminho feliz; `state` errado; código usado/vencido; `aud` ou `iss` trocados; `exp` vencido; assinatura inválida (chave de outra pessoa); `alg=none` e HS256 recusados; cargo desconhecido; organização desconhecida; e-mail já vinculado a outro; matrícula suspensa; Central fora do ar (nunca 500); nada sensível no log.

## Escola nova (organização que ainda não tem escola no APM)
Dito pelo dono do produto: **organização + produto cria um ambiente vazio**. Proposta: o primeiro acesso de uma organização desconhecida **cria a escola vazia** (nome vindo do token, se a Central mandar; senão "Minha escola" e a Secretaria acerta em Configurações), com a pessoa como `secretaria` **somente se o cargo da Central for `secretaria`**; funcionário que chega antes da escola existir é recusado (`org`). Isso exige as respostas da seção seguinte.

## O que falta para produção (a Forklin precisa responder)
1. **Várias escolas por produto.** O ADR 0011 da Central diz que cada instalação pertence a **uma organização** e que a credencial do produto é **por (produto, organização)**; "vários tenants por organização×produto" está adiado. O APM é **uma instalação para muitas escolas**. Preciso de uma destas: (a) credencial do produto **sem organização** válida na troca do código; (b) uma credencial por escola (fica pesado operar); (c) a Central aceitar o modelo "organização = escola" com `/product-api/v1` por organização no corpo. Sem isso o cadastro de funcionários pela Central (`credential_org_required`) não funciona para o APM.
2. **O nome da organização** no token (ou um endpoint para ler), para a escola nova nascer com nome.
3. **Cadastro do APM no painel "Novo sistema":** Nome `APM Digital`, Slug `apm-digital` (é o `aud`), URL base (**o domínio público do APM**), Descrição, e os cargos `secretaria` e `funcionario`.
4. **URL da API Central**, o **segredo do produto** (só no ambiente, nunca no chat) e o JWKS acessível do servidor do APM.
5. Confirmar que o campo `role` do token traz exatamente `secretaria` / `funcionario`.
6. Decidir se **cada escola é uma organização** (a regra do APM é uma escola por conta, então a resposta natural é sim).
7. Revisão de segurança independente do fluxo de login antes de ligar com dinheiro real.

## Fora do escopo
2FA (decidido no ADR-016 para antes de produção com dinheiro real), receptor de eventos de revogação (fase 3), desligar a senha local, e importar usuários antigos em lote.

## Rollback
`FORKLIN_CORE_ENABLED=false` e reiniciar: o botão some e `/sso/*` volta a 404; quem entrou pela Central e não tem senha local usa "esqueci a senha". A migração 0023 só acrescenta duas colunas nuláveis (downgrade as remove). **Irreversível:** usuários criados na Central (dá para desativar, não "des-criar").
