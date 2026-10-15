# Funcionários da APM: hoje (MVP) e no ecossistema Forklin

Escrito em 2026-10-15, a partir do código do Diário Digital (branch `origin/integracao`) e da API Central. **Nada disto está ligado ainda no APM Digital**: é o plano para quando a integração chegar.

## 1. Hoje (MVP): a gestão traz o funcionário pelo próprio sistema da APM
- **Tela "Equipe"** (`/painel/equipe`) e **rotas `/api/v1/employees`**, para quem tem a permissão de convidar (`invitations:create`: administrador da escola e **gestão**).
- A gestão informa **nome, e-mail e cargo** (padrão: funcionário). O sistema manda um **e-mail** (Resend) com um link de 72 horas para a pessoa escolher a senha. A gestão vê quem já faz parte da equipe e quem ainda não entrou, **reenvia** ou **cancela** o convite, e **suspende** ou **reativa** o acesso de um funcionário.
- Regra de quem pode o quê: quem pode convidar um cargo pode também suspender e reativar esse cargo, **nunca a si mesmo**. A gestão traz **só funcionários**; o administrador pode trazer qualquer cargo.
- O e-mail e a regra moram em **um único ponto** (`app/auth/invite.py`). É esse ponto que será trocado na integração; as rotas e a tela ficam.

## 2. Como o Diário Digital faz (o exemplo a seguir)
1. **Cadastro.** `POST /api/professores` (gestão ou secretaria) pede e-mail, nome e tipo. Com a chave `FORKLIN_CORE_ENABLED` **desligada** é o convite local (conta pendente + e-mail de ativação). **Ligada**, o cadastro vai para a **Central**.
2. **Central primeiro.** O Diário chama a API da Central (`POST /product-api/v1/users`, ou `/users:batch` com até 50 de uma vez, atômico) com `Authorization: Bearer <segredo do produto>` e `Idempotency-Key`. Timeout de 3 s. A Central é a dona da identidade, cria o usuário e manda o **convite da Forklin** (a pessoa escolhe a senha lá).
3. **Só depois grava local.** O Diário só grava o usuário e o perfil na escola **depois** de a Central confirmar (201 ou 200). O usuário local nasce **ativo, sem senha local, com o mesmo id da Central** (`central_user_id`). Central fora do ar: **503 e nada gravado**. Se a gravação local falha depois de criar na Central, o Diário **desativa** o usuário na Central (compensação).
4. **Entrada por SSO.** A pessoa abre o **App Forklin**, vê o produto (aqui, o APM Digital) e clica em **Acessar**. O App pede um código de uso único (60 s) à Central e redireciona para `{produto}/sso/callback?code=`. O produto troca o código por um **JWT curto (10 min, assinatura EdDSA)** e confere a assinatura pela chave pública da Central (JWKS).
5. **Provisionar no primeiro acesso** (`forklin-provisionar.ts`). Confere que a organização do token é a dona da instalação; traduz o cargo da Central (`role`) para o papel local (cargo desconhecido: recusa, nunca assume um padrão); acha o usuário pelo id da Central, ou por e-mail só se ainda **não** tiver vínculo; cria se não existir; **nunca reativa** quem está desativado ou suspenso no produto; atualiza nome e cargo.
6. **Mudar o acesso** (suspender, reativar, desativar) é feito **na Central** (`PATCH /users/{id}` com `active`, `suspended` ou `disabled`) e o Diário só altera o local depois.
7. **Limite de vagas** (`seat_limit`), organização inativa e e-mail de outra organização voltam como erros da Central e viram frases na tela.

## 3. O que o APM Digital fará (quando a integração chegar)
| Hoje | Na integração |
|---|---|
| `issue_invitation` manda e-mail do APM | Chama a Central (`POST /users`) e a Central manda o e-mail do App |
| Pessoa escolhe senha no APM | Pessoa escolhe senha na Forklin; no APM **não há senha local** |
| Login por e-mail e senha | **SSO**: App → Acessar → `/sso/callback` |
| `users.id` próprio | `users.central_user_id` (id da Central) e provisionar no primeiro acesso |
| Suspender muda a matrícula daqui | Muda na Central (`PATCH`) e depois aqui |
| Cargos `school_admin`, `treasurer` (gestão), `staff`, `viewer` | Mapa **cargo da Central ↔ cargo do APM** (tabela fixa, cargo desconhecido recusado) |

Pontos a criar ao integrar: coluna `central_user_id` em `users`; tabela das organizações/escolas ligadas à Central (`central_org_id` na escola, como `rede_escolar.central_org_id` no Diário); rota `/sso/callback` e `/sso/start`; cliente da Central com os mesmos limites do Diário; a chave `FORKLIN_CORE_ENABLED` (já existe e hoje **recusa subir ligada**) e os segredos só no ambiente.

## 4. O que ainda preciso confirmar com quem cuida da Central
1. Os **`role_key`** que o APM terá na Central (hoje só existem os do Diário: `secretaria`, `gestao`, `professor_titular`, `professor_especialista`) e como a Central trata o cargo `gestao` do APM.
2. Se **cada escola do APM é uma organização** da Central (o Diário usa "uma organização = uma rede = uma escola").
3. Como o produto **APM Digital** será cadastrado na Central (`organization_products`, `max_users`, URL base do callback) e onde fica o segredo do produto.
4. O que acontece com **funcionários que já existem** no APM quando a integração ligar (vinculação por e-mail, como o Diário faz para os usuários antigos).
