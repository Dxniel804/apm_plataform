# Gateway de pagamento: preparação e decisão (2026-10-15)

Candidatos: **Asaas** e **Pagar.me**. Decisões já tomadas: só Pix; sem split e sem porcentagem para a Forklin (receita = mensalidade pela Central); o link da escola decide o destino do dinheiro; a escola não lida com o gateway (a Forklin cadastra o destinatário); a tarifa do Pix é absorvida pela escola (**A**) por enquanto.

## 1. O que já está pronto no sistema
| Peça | Estado |
|---|---|
| Interface `PixProvider` (`create_charge`, `fetch_payment`) | Pronta. O sandbox a implementa |
| Webhook tratado como **afirmação não confiável**: autentica, grava o evento uma vez, **pergunta ao provedor** o que aconteceu e confere o valor | Pronto (M4) |
| Tarifa do gateway por pagamento (`contribution_fees`) | Pronta; o adaptador só precisa informar `fee_cents` |
| Contas de pagamento por escola (`payment_accounts`) com `secret_ref` (`env:NOME`), nunca a chave no banco | Pronto |
| Nomes `ASAAS` e `PAGARME` aceitos no banco | Migração 0020 |
| **Chave liga/desliga** `PIX_LIVE_ENABLED` (desligada por padrão) | Pronta: provedor real só é servido com adaptador **e** a chave ligada; senão 503 `payments_paused` |
| **Testes de contrato** de qualquer adaptador (`tests/pix/test_provider_contract.py`) | Prontos; o sandbox passa. O adaptador novo entra na lista `ADAPTERS` e precisa passar nos mesmos testes |
| E-mail real (Resend) | Pronto (M10, parte 1) |

## 2. O que falta quando o gateway for escolhido
1. Escrever o adaptador (`app/pix/asaas.py` ou `pagarme.py`) e registrá-lo em `REAL_PROVIDERS`.
2. Uma rota de webhook própria (`/webhooks/pix/asaas` ou `/pagarme`) com a **autenticação desse gateway**, e listá-la em `ORIGIN_EXEMPT_PATHS`. Verificar a assinatura se houver; **sempre** reconsultar o pagamento na API do gateway.
3. Cadastro do destinatário pela equipe da Forklin (CNPJ da APM, conta de liquidação), guardando só o identificador e a referência da chave (`env:`).
4. Ensaio no sandbox do gateway, depois **um pagamento real de valor mínimo**, com `PIX_LIVE_ENABLED=true` só no ambiente do ensaio.
5. **Liquidação e conciliação** (ver 4).
6. Reembolso por API (devolução de Pix), se for oferecido.

## 3. Comparação (o que li e o que ficou em aberto)
| Critério | Asaas | Pagar.me |
|---|---|---|
| **Preço por Pix recebido** | **R$ 1,99** (R$ 0,99 nos 3 primeiros meses). Em uma contribuição de R$ 20 isso é ~10% | **0,99%** (≈ R$ 0,20 em R$ 20). Minimos e mensalidade: **não confirmados** |
| Conta do destinatário | **Subconta** com saldo, carteira (`walletId`) e `apiKey` próprios, no CNPJ da APM. O dinheiro fica na conta Asaas da APM e precisa ser transferido ao banco | **Recebedor** com conta bancária de liquidação (a confirmar: cair direto na conta do Banco do Brasil da APM) |
| Onboarding | API `POST /v3/accounts`. Modo comum: o titular recebe e-mail e envia documentos pelo site do Asaas. Modo BaaS: a plataforma conduz, com configuração prévia e **período de avaliação** (até 10 subcontas, R$ 2.000 por subconta, 60 dias) | Não confirmado (o plano antigo diz "recebedores reais") |
| Webhook | Token fixo (`authToken`) configurável; recomenda processar de forma idempotente. É compatível com o nosso desenho (reconsulta) | Autenticação **não confirmada** |
| Sandbox | Existe, com limite de 20 subcontas por dia. Pagamento de Pix: confirmação manual pelo painel; **por API, não confirmado** | **Não confirmado** |
| Documentação encontrada | Boa e pública | Parcial; páginas v5 de recebedores não localizadas |

**Observação importante sobre o preço.** Com contribuições de R$ 10 a R$ 50, uma tarifa fixa de R$ 1,99 pesa de 4% a 20% da contribuição. Com a decisão atual (**A**, a escola absorve), isso come uma parte relevante do que a escola recebe. Pagar.me, com percentual, custa de R$ 0,10 a R$ 0,50. Se o Asaas for o escolhido, vale **negociar o preço por volume** ou reabrir a decisão da tarifa (opção B ou C).

## 4. A conciliação muda com um gateway
Hoje a conciliação compara cada Pix do sistema com a linha do extrato do banco. Com um gateway no meio, o extrato do **Banco do Brasil mostrará as liquidações** (transferências do gateway para a conta, em lotes), e não cada Pix. Então, junto com o adaptador, será preciso:
- importar o **relatório de liquidação** do gateway (API ou arquivo), que lista cada Pix e a qual liquidação pertence;
- conciliar **Pix do sistema ↔ liquidação do gateway** e **liquidação ↔ linha do extrato do BB**.

Isso é um critério de escolha: qual gateway entrega o extrato ou relatório de liquidação por API, com o identificador fim a fim do Pix.

## 5. Perguntas para tirar com o comercial de cada um (as respostas decidem)
1. A APM é uma **associação sem fins lucrativos** com CNPJ. É possível abrir a conta ou o recebedor por API? Quais documentos e quanto tempo leva?
2. **Onde o dinheiro cai?** Direto na conta do Banco do Brasil da APM? Em que prazo (D+0, D+1)?
3. **Preço por Pix recebido** para valores de R$ 10 a R$ 50: há mínimo, mensalidade ou taxa por conta aberta? Há desconto por volume (muitas escolas)?
4. A **Forklin**, com o próprio CNPJ, pode abrir contas para terceiros por API? Há contrato de marketplace, aprovação prévia ou limite de contas?
5. **Webhook**: como é autenticado (assinatura HMAC ou token)? Quantas tentativas e em que intervalo? Há o identificador fim a fim do Pix no aviso?
6. **Ambiente de testes**: dá para **simular o pagamento de um Pix por API**?
7. Existe **relatório de liquidação por API**, com o identificador fim a fim de cada Pix?
8. **Devolução de Pix** por API? E o tratamento de devolução por fraude (MED)?
9. O gateway cobra algo da **Forklin** por intermediar contas de terceiros? Quem responde perante o Banco Central?

## 6. Regras que valem para qualquer gateway
- A chave de API fica só no ambiente (`secret_ref = env:NOME`), nunca no repositório, no banco, em log ou no chat.
- Nenhum pagamento real sem `PIX_LIVE_ENABLED=true`. Para parar de cobrar, desligue e reinicie a API.
- O sandbox nunca é servido em produção.
- Toda notificação é uma afirmação: confirmar sempre na API do gateway.

## 7. Variáveis de ambiente (o `.env.example` não vai mais para o repositório)
| Variável | Para quê | Padrão |
|---|---|---|
| `PIX_LIVE_ENABLED` | Liga os provedores **reais** de Pix. Só a palavra `true` liga | `false` |
| `EMAIL_SENDER` | `file` (só desenvolvimento) ou `resend` | `file` |
| `RESEND_API_KEY` | Chave do Resend. **Só no `.env`/ambiente, nunca no chat** | vazia |
| `MAIL_FROM` | Remetente de um domínio verificado no Resend | vazio |
| Chave do gateway | Uma variável por escola ou conta, referenciada por `payment_accounts.secret_ref = env:NOME` | — |
