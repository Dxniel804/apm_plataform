# Impostos retidos e a "cola" para a Receita (migração 0029)

Item D do plano (`docs/thelastversion.md`), em formato que **não decide a lei e não fala com o governo**.

## O que faz
- A escola escreve as **regras**, lendo a lei e os sites do governo (`tax_rules`): alíquota, teto da base, código da guia (4 números) ou como pagar, dia do vencimento (no mês seguinte) e o que fazer se cair em fim de semana.
- Cada serviço pago com retenção vira uma **retenção** (`tax_retentions`): empresa ou pessoa física, nome, mês do serviço (a competência), valor bruto. O sistema calcula a base (até o teto), o valor retido (base × alíquota, arredondado para o centavo, meio para cima, sem decimais de ponto flutuante) e quanto se paga ao prestador.
- Por imposto e por mês, a **guia** soma as retenções que não foram anuladas e mostra o que digitar no site da Receita: valor, código, período de apuração e vencimento. A tela tem um botão para abrir o site (`RECEITA_SICALC_URL` em `app/tax/service.py`: **confira o endereço**, governos mudam de site).
- Pagar a guia é uma despesa comum, na categoria nova "Impostos retidos e tributos pagos" (`tax_payments`). Nada aqui mexe no razão financeiro.

## O que NÃO faz, de propósito
- **Não traz alíquota nem vencimento como verdade.** Em 19/10/2026 só achei fontes não oficiais, que se contradizem no prazo (um fala "último dia útil do 2º decêndio", outro "3º dia útil da semana seguinte"), e a tributação de pessoa física está mudando em 2026. Por isso a lista de regras começa **vazia**; o que existe são três **sugestões não validadas** (IRRF de serviço profissional de empresa a 1,5% com o código 1708; INSS de autônomo a 11%; ISS municipal sem alíquota), todas sem vencimento.
- Uma regra só aparece como **conferida** se alguém marcar que a leu numa fonte oficial **e anotar o endereço dela** (a API recusa a marca sem a fonte; guarda quem e quando). Sem isso, a guia mostra "a regra ainda não foi conferida: não pague com base neste valor antes de conferir no site do governo".
- Não considera feriados no vencimento, não emite DARF, não gera o código de barras, não envia DCTFWeb, EFD-Reinf nem eSocial.
- Não guarda CPF nem CNPJ de quem recebeu: pergunta só se é pessoa física ou empresa e o nome.

## Como as regras mudam sem apagar o passado
`tax_rules` só recebe linhas. Mudar uma regra é inserir uma nova versão com o mesmo `rule_key`; a última conta. Cada retenção guarda **a versão exata** que usou (e a alíquota), então o que foi calculado nunca muda. Se um mês tem retenções de versões diferentes, a guia avisa.

## O que conferir numa fonte oficial (antes de marcar "conferida")
Não há contadora para perguntar, então cada ponto abaixo se confere nos sites do governo, e o endereço vai no campo "Fonte oficial" da regra:
1. O código e a alíquota de cada imposto que a APM retém, e se a APM é obrigada a reter (associação sem fins lucrativos, prestador MEI ou com declaração de isenção podem mudar o resultado).
2. O vencimento de cada um.
3. O valor mínimo da guia e o que se faz com o saldo abaixo dele.
4. **Como** o INSS retido é recolhido hoje (eSocial e DCTFWeb, com certificado digital, ou outra forma).
5. A alíquota do ISS do município e a forma de pagar.

## Rotas
Todas em `/api/v1/schools/{id}/tax`, permissão `months:close`: `GET /rules`, `POST /rules`, `GET /preview`, `GET /month?period=`, `POST /retentions`, `POST /retentions/{id}/void`.
