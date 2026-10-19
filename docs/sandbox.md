# Sandbox: uma escola de mentira, com setembro e outubro prontos

Serve para olhar e entender o produto com dados parecidos com os de uma escola que comprou o APM Digital em setembro de 2026. **Tudo é inventado** (nomes, valores, notas) e **só existe na máquina local**: o gerador (`app/seed_sandbox.py`) recusa rodar com `ENV=production`.

## Como subir
```
source ~/forklin-central-local/apm-sandbox.env.sh   # portas 8040 (API), 5490 (banco), 3104 (site)
docker compose up -d --build api
docker compose --profile tools run --rm tools python -m app.seed_sandbox
~/forklin-central-local/subir-local.sh                # liga o site em http://localhost:3104
```
O gerador imprime o login uma vez; a senha é gerada na hora (ou `SEED_PASSWORD`). Para apagar tudo e começar de novo: `docker compose down -v` na mesma pasta e rodar de novo.

## O que a escola "EMEB Sol Nascente (sandbox)" tem
- **Pessoas:** uma secretaria (gestão) e uma funcionária (só pede despesas).
- **Saldo de quando começou** (digitado no balancete): banco R$ 18.400,00, caixa R$ 650,00, aplicação R$ 2.000,00. O livro caixa parte de zero.
- **Setembro (fechado) e outubro (aberto, até o dia 18):** contribuições por Pix pela página da escola, Pix direto na conta, dinheiro, uma doação e dois Pix com valor diferente do esperado (em revisão); despesas em todas as situações (pagas, aguardando aprovação, correção pedida, rascunho, aprovada sem pagar), reembolsos (um pago e um a pagar), uma devolução e as tarifas do banco.
- **Dois extratos de banco importados:** a conta da APM e a conta do PDDE, em setembro e outubro. Na conta da APM há um Pix que ninguém registrou, uma tarifa que o livro não tem e, no livro, um pagamento sem linha no extrato: a conciliação mostra cada um.
- **PDDE:** o **formulário do FNDE** (Demonstrativo) do Básico já sai preenchido (entidade fictícia, CNPJ dos fornecedores, número da ordem bancária, rendimento, devolução e saldo de R$ 1.200,00 que veio de 2025); repasses do Básico (custeio e capital) e do Educação Conectada; despesas com documentos (uma comprovada, uma só em parte), uma sem classificação, uma tarifa do banco na conta do PDDE (o aviso aparece) e um reparo classificado como capital (o aviso de "gastou mais em capital do que recebeu" aparece).
- **Impostos:** três regras de exemplo (as duas primeiras **não conferidas**, a do ISS marcada como conferida com uma fonte que diz "exemplo inventado") e quatro retenções (duas em setembro, duas em outubro, uma delas abaixo do valor mínimo da guia).

## Dois números que parecem errados e não são
1. **No Fechamento de setembro, a "diferença do banco" é de cerca de R$ 17.700.** O livro começa em zero e o saldo de R$ 21.050,00 de antes do sistema só entra no **balancete**, não no fechamento (pendência registrada em `docs/security-self-review-m8-balancete.md`, achado 4).
2. **No balancete de outubro o caixa aparece igual ao de setembro**: ninguém digitou o caixa de outubro. Digite em Fechamento, "Onde está o dinheiro no fim de outubro".
