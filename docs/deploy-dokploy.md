# Implantação do APM Digital no Dokploy

Para quem opera o Dokploy. Nada aqui tem segredo: **os valores ficam só nas variáveis do Dokploy**
(o repositório é público e o CI varre o histórico atrás de credenciais).

O compose (`deploy/docker-compose.yml`) e o `Dockerfile` do site (`apps/web/Dockerfile`) foram
**ensaiados** numa pilha local com `ENV=production`, um Postgres 16 separado e as mesmas imagens
(resultado na seção [Ensaio](#ensaio-feito)).

## O que sobe

```
internet ──HTTPS──> Traefik (Dokploy)
                      ├─ apm.exemplo.com.br        ──> web  :3000   (Next.js: telas, /sso/*)
                      └─ apm.exemplo.com.br/api    ──> api  :8000   (FastAPI: /api/*)
                                                        │
                      jobs (expira Pix a cada minuto) ──┤
                      migrate (1 vez por versão) ───────┤
                                                        v
                                     Postgres 16 SÓ DO APM  (serviço do Dokploy, backup agendado)
```

- **Um domínio só** para o site e a API (cookies e a checagem de origem exigem isso). Nenhuma porta é
  publicada: o Traefik fala com os serviços pela rede interna.
- **Banco dedicado.** Papéis `apm_owner`, `apm_app` e `apm_definer` são criados pela migração e valem
  para o servidor inteiro, por isso o Postgres é só do APM.

## 0. Antes de começar
- Um **endereço** para o APM (por exemplo `apm.forklin.com.br`) com o DNS apontando para o servidor.
- Um domínio verificado no **Resend** e um remetente (`MAIL_FROM`), para convites e recuperação de senha.
- (Quando for ligar a Forklin) o código da Central, do App e do Admin já implantado: ver o passo 5.

## 1. O banco (serviço Postgres do Dokploy)
1. Crie um serviço **Postgres 16** (o APM foi testado no 16), por exemplo com o nome `apm-db`.
2. Banco `apm`, usuário `apm_admin` (administrador do **servidor deste contêiner**, que é só do APM) e
   uma senha forte. **Sem porta externa.**
3. Anote o **nome interno** do serviço: é o `DB_HOST` do passo 2.
4. Ative o **backup agendado** do banco para um destino S3/R2 (diário, com retenção). O passo
   [Backup e restauração](#backup-e-restauração) inclui os anexos.

O usuário `apm_admin` só é usado pelo serviço `migrate` (e para backup). A API e o job conectam como
`apm_app`, que **a própria migração cria**, com a senha que vem da `DATABASE_URL`.

## 2. A aplicação (Docker Compose do Dokploy)
Crie uma aplicação do tipo **Compose**: repositório do APM, branch `main`, caminho
`./deploy/docker-compose.yml`. Variáveis (aba *Environment*):

| Variável | Obrigatória | Valor |
|---|---|---|
| `APM_DOMAIN` | sim | `apm.exemplo.com.br` (sem `https://`) |
| `DB_HOST` | sim | nome interno do serviço Postgres do passo 1 |
| `DB_NAME` | não | `apm` (padrão) |
| `DB_ADMIN_USER` | sim | `apm_admin` |
| `DB_ADMIN_PASSWORD` | sim | senha do passo 1 |
| `APP_DB_PASSWORD` | sim | senha **nova** do papel `apm_app`. Vai dentro de uma URL: use só letras e números (`openssl rand -hex 24`) |
| `AUTH_SECRET` | sim | `openssl rand -hex 32` (assina o CSRF e as chaves de limite de tentativas; **guarde: trocar derruba as sessões**) |
| `RESEND_API_KEY` | sim | chave do Resend |
| `MAIL_FROM` | sim | `APM Digital <contato@seudominio.com.br>` (domínio verificado no Resend) |
| `PIX_LIVE_ENABLED` | não | **`false`** (padrão): contribuições respondem "pagamentos pausados" até o gateway ser escolhido |
| `FORKLIN_CORE_ENABLED` | não | `false` até o passo 5; depois `true` |
| `API_CENTRAL_URL` | com a Forklin | URL **interna** da Central, só o nome do serviço na rede do Dokploy (como a do App: `http://<servico>:8000`, sem pontos no nome), ou a pública `https://`. Qualquer outro `http://` é recusado em produção |
| `FORKLIN_APP_URL` | com a Forklin | `https://` do App Forklin |
| `FORKLIN_PRODUCT_SLUG` | não | `apm-digital` (padrão) |
| `FORKLIN_PRODUCT_SECRET` | com a Forklin | o segredo que a Central mostrou **uma vez** no passo 5 |
| `TRUSTED_PROXY_IPS` | não | `*` (padrão): a API só é alcançada pelo Traefik |

A API **recusa subir** com `ENV=production` sem HTTPS, `COOKIE_SECURE`, origens `https`, e-mail pelo
Resend ou `AUTH_SECRET` forte: isso já está no compose, e a mensagem de erro diz o que falta.

**Domínios** (aba *Domains* da aplicação), os dois com HTTPS (Let's Encrypt):

| Host | Caminho | Serviço | Porta | Remover o prefixo |
|---|---|---|---|---|
| `apm.exemplo.com.br` | `/` | `web` | 3000 | – |
| `apm.exemplo.com.br` | `/api` | `api` | 8000 | **desligado** (a API espera `/api/...`) |

## 3. Primeira implantação
Clique em *Deploy*. A ordem é automática: `migrate` (cria papéis, tabelas, políticas e permissões e
termina), depois `api` e `jobs`, depois `web`. Se o `migrate` falhar, nada mais sobe: leia o log dele
(erros comuns: `DB_HOST` errado, senha do administrador errada, `APP_DB_PASSWORD` com caracteres
especiais na URL).

## 4. Conferir
- `https://<dominio>/api/health` → `{"status":"ok"}` e `https://<dominio>/api/health/ready` → pronto
  (fala com o banco).
- `https://<dominio>/login` abre a tela de entrada.
- `https://<dominio>/api/docs` **não** existe (404). A API confere as permissões do banco ao subir e se
  recusa a funcionar se algo estiver fora do desenho.
- Nos logs da API: sem linha de erro; do `jobs`: só aparece algo quando expira alguma cobrança.

## 5. Ligar o APM ao ecossistema Forklin
Na ordem (cada item na ferramenta indicada):
1. **Admin de produção → Novo sistema:** Nome `APM Digital`, Slug `apm-digital`, **URL base**
   `https://<dominio>` (sem barra no fim), Descrição, e os cargos `secretaria` e `funcionario`.
2. **Central de produção** (terminal do Dokploy, no contêiner da Central):
   `python -m central_api.cli set-product-events-url --product apm-digital --url https://<dominio>/api/v1/forklin/events`
   e `python -m central_api.cli create-product-credential --product apm-digital`. O segundo mostra o
   segredo **uma única vez**: copie direto para `FORKLIN_PRODUCT_SECRET` do APM (nunca para chat ou
   e-mail).
3. **Central:** `PRODUCT_EVENTS_ENABLED=true` (reimplantar a Central). **App:** acrescentar em
   `PRODUCT_LOGIN_URLS` a entrada `"apm-digital":"https://<dominio>/login"` (sem tirar a do Diário) e
   reimplantar o App.
4. **APM:** `FORKLIN_CORE_ENABLED=true`, `API_CENTRAL_URL`, `FORKLIN_APP_URL` e o segredo; reimplantar.
5. **Teste com uma organização de teste:** contratar o APM para ela no Admin (o ambiente deve nascer em
   segundos), criar uma pessoa com cargo `secretaria`, entrar pelo App → *Acessar*, e testar o botão
   *Entrar com Forklin* da tela do APM e o caso de uma pessoa **sem acesso** (volta ao login do APM com
   o aviso). Organizações que já tinham o APM contratado antes: `resend-product-notices --product apm-digital`.

Detalhes e o raciocínio: [adr-forklin-sso.md](adr-forklin-sso.md).

## Backup e restauração
São **duas** coisas, e as duas entram no plano:
1. **O banco** (serviço Postgres do Dokploy): backup agendado para S3/R2, retenção definida.
2. **O volume de anexos** (`attachments`, no compose): fotos de notas e comprovantes. Se o Dokploy da
   sua versão faz backup de volume, use; senão, um comando agendado no servidor:
   `docker run --rm -v <projeto>_attachments:/data -v /caminho/backup:/backup alpine tar czf /backup/anexos-$(date +%F).tgz -C /data .`
   e envio do arquivo ao S3/R2.

**O livro financeiro não aceita apagar linhas** (gatilhos). Restaure **sempre o banco inteiro**, nunca
"arrumando um pedaço".

**Teste a restauração antes de ligar dinheiro real**, num banco novo, nunca por cima do de produção:
1. Crie um Postgres 16 temporário e restaure o último backup nele.
2. Suba a API de um ambiente de teste apontando para ele (ou rode `python -m app.posture` com a
   `DATABASE_URL` dele): a verificação de permissões tem de passar.
3. Confira que o fechamento de um mês bate (o código de verificação do fechamento é recalculado).
4. Restaure o volume de anexos e confira que uma foto abre.

## Atualizações e volta
- **Nova versão:** *Deploy* de novo. O `migrate` roda antes da API; as migrações são **aditivas**
  (a API antiga continua funcionando durante a troca).
- **Voltar uma versão:** reimplante o commit anterior. Só use `alembic downgrade` com a janela de
  manutenção e o backup do dia em mãos.
- **Girar o `AUTH_SECRET`:** derruba as sessões (todos entram de novo).

## Antes de ligar dinheiro de verdade
Não é parte desta implantação, mas fica registrado: escolher e integrar o **gateway** Pix
([gateway-integration.md](gateway-integration.md)), a **revisão de segurança independente** do login,
o **2FA** da secretaria e o **teste de restauração** acima. Até lá o APM funciona com `PIX_LIVE_ENABLED=false`.

## Ensaio feito
Pilha local com as mesmas imagens e `ENV=production`: migração a partir do banco vazio, API saudável,
`jobs` ativo, site respondendo e repassando `/api` à API pela rede interna, `/api/docs` e a rota de
simulação de Pix respondendo 404, volume de anexos gravável pelo usuário da API.
