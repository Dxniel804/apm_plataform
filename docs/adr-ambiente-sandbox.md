# ADR: ambiente Sandbox ou Produção no APM (primeira parte: o modo)

**Status:** implementado (branch `feat/org-environment`; chave desligada por padrão) · segue o ADR do ambiente da Central
(`api_central`, `docs/adr/NNNN-ambiente-sandbox-producao.md`) e estende [adr-forklin-sso.md](adr-forklin-sso.md).

## O que o APM faz
A Central decide, por organização, se todos os produtos dela rodam em demonstração (`sandbox`) ou de
verdade (`production`). O APM **só registra** o que a Central diz e mostra isso. Esta parte **não muda o
Pix** (a segunda e a terceira partes: `is_demo` nos dados do negócio e o Pix de teste persistente).

- **Coluna `organizations.environment`** (migração 0033). As organizações que já existem ficam
  `production` (já operam; nada real vira demonstração). O padrão de uma nova é `sandbox`.
- **Como chega:**
  1. o aviso `organization.product_contracted` pode trazer `environment`;
  2. o evento `organization.environment_changed` (`environment` obrigatório; outro valor é 400);
  3. o claim `org_env` do token de cada entrada (recupera um aviso perdido).
  Qualquer valor fora de `sandbox`/`production` é ignorado. Token sem o claim não muda nada.
- **Quem grava:** só a função `set_forklin_environment(central_org_id, environment)`, do `apm_definer`,
  para organizações que vieram da Central. Organização desconhecida é um não-fazer que responde como um
  acerto.
- **Corrige uma folga:** o papel da aplicação (`apm_app`) podia atualizar **todas** as colunas de
  `organizations` (grant de tabela). Agora só `name` e `updated_at`: nenhuma sessão de escola muda o
  próprio modo, nem o `central_org_id`.
- **Tela:** `GET /api/v1/environment` (qualquer pessoa com sessão) devolve o modo; o painel mostra a faixa
  "Você está no ambiente de demonstração. Os dados desta escola são de demonstração." em `sandbox`. A faixa
  **não** diz "nenhum pagamento real" enquanto o Pix real não for recusado em sandbox (parte seguinte). Atrás de `FORKLIN_ENVIRONMENT_ENABLED` (padrão
  `false`): desligada, a rota responde `null` e nada na tela muda.

## Parte 2: o link dos pais em sandbox (migração 0034)
- Não existe gateway real (`REAL_PROVIDERS` está vazio): o banco de mentira é o único banco. Em produção ele só é
  servido a uma organização em `sandbox` (`get_provider(..., sandbox_org=True)`); a rota de "pagar" dele
  (`/dev/sandbox/pix/{txid}/pay`) idem, e responde 404 para qualquer outra.
- A função `sync_sandbox_payment_account(central_org_id)` dá à escola em sandbox uma conta SIMULADA (provider
  `SANDBOX`, id `sandbox`) e a desliga (`INACTIVE`) quando a escola vai para produção. Roda quando o modo chega
  (aviso, evento ou token), só com `FORKLIN_ENVIRONMENT_ENABLED` ligada.
- Sem conta ativa a escola não resolve (404): por isso a conta nasce junto com o modo, antes de alguém abrir o link.
- A página pública devolve `environment`; em `sandbox` o site mostra o card "Ambiente de demonstração" antes da
  contribuição. Escola em produção não passa pelo card.
- A função `school_has_active_account` existe porque a política antiga de `schools` lia `payment_accounts` e, ao
  gravar uma conta como `apm_definer`, o Postgres recusava o laço entre as políticas.

## Parte 3: `is_demo` (migração 0035)
- 24 tabelas de atividade (livro, Pix, despesas, campanhas, pedidos, extratos, PDDE, retenções) ganham `is_demo`.
  A configuração da escola (categorias, contas, regras, entidades) não.
- Um gatilho marca `is_demo` na criação (organização da Central em sandbox). Ninguém precisa lembrar de marcar.
- `hides_demo()` + uma política RESTRITIVA por tabela (`<tabela>_hide_demo`) escondem o que é demonstração de uma
  organização em produção. Nenhuma consulta, relatório ou exportação precisa saber disso.
- As chaves de negócio que um registro escondido poderia usar para travar um real (código de referência do
  lançamento, fechamento do mês, mesmo extrato, mesma linha, mesma chave de nota) valem só entre os reais.
- Organização que não vem da Central (desenvolvimento, testes) nunca é marcada nem escondida.

## Parte 4: a escola em sandbox já vem com dados (`app/demo.py`)
- **Quando:** na primeira entrada de uma **secretaria** numa escola em `sandbox` (chave ligada) que ainda **não tem
  nenhum lançamento**. A escola, as categorias e a conta de pagamento simulada já nascem quando o produto é
  contratado; os dados esperam essa primeira entrada porque os registros precisam de uma pessoa como autora e a
  escola só tem pessoas depois que alguém entra.
- **Como:** com a permissão normal da API, dentro do tenant da escola (os mesmos gatilhos e políticas de qualquer
  pedido; nada é contornado). A pessoa que entra é a autora; nenhum usuário falso é criado. O banco marca tudo como
  `is_demo` (parte 3), então some ao ir para produção.
- **Segurança:** escola que já tem qualquer lançamento **nunca** é preenchida (uma escola de verdade mandada para
  sandbox não é tocada); há trava (`pg_advisory_xact_lock`) contra duas primeiras entradas ao mesmo tempo; falha no
  preenchimento só é registrada no log e nunca atrapalha o login.
- **O que vem:** um mês fechado e o mês corrente (datas relativas a hoje): Pix da página dos pais (um pendente),
  Pix direto, dinheiro, uma doação, tarifas bancárias e despesas aguardando decisão (enviada, correção pedida,
  rascunho).
- **O que NÃO vem (ainda):** despesas aprovadas/pagas e reembolso (ninguém decide uma despesa que enviou e a escola
  tem uma pessoa só), extratos bancários e conciliação, PDDE, retenções de imposto, balancete, campanhas e o
  fechamento do mês. O script `seed_sandbox` tem tudo isso, mas precisa da senha de administrador do banco, que a
  API não tem de propósito.
- **Outros produtos:** Diário e Patrimônio ainda não leem o modo nem criam dados de demonstração.

## Ligar em produção (ordem)
1. Central com `ORG_ENVIRONMENT_ENABLED=true` (token com `org_env`, avisos com `environment`).
2. Migração 0033 no APM (aditiva; as escolas atuais ficam `production`).
3. `FORKLIN_ENVIRONMENT_ENABLED=true` no APM. **Antes do passo 1, uma escola criada pela Central nasce
   `sandbox` aqui** (padrão seguro) e só vira `production` quando a Central disser.

## Rollback
`FORKLIN_ENVIRONMENT_ENABLED=false` (a faixa some e a rota responde `null`). A migração tem `downgrade`
(devolve o grant de `UPDATE` da tabela inteira ao `apm_app` e remove a coluna e a função).
