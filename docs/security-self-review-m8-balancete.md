# Autorrevisão de segurança: balancete e PDDE (2026-10-19)

**Isto NÃO é a revisão independente do M9.** É a minha leitura do que foi construído nas migrações 0027
(balancete) e 0028 (PDDE), e do que mudou no leitor de PDF, para o revisor chegar com os pontos já levantados.
Quem escreveu o código não pode ser o revisor independente: ela continua pendente e é condição para ligar
dinheiro real.

## O que olhei
`balancete_balances`, `pdde_classifications`, `pdde_documents` (tabelas, gatilhos, funções, RLS, permissões),
as rotas de `/balancete` e `/pdde`, os relatórios (PDF e planilha) e o leitor de PDF.

## Pontos que estão bem
| Ponto | Como está |
|---|---|
| Perímetro privilegiado | Nenhuma função `SECURITY DEFINER` nova, nenhuma política para o `apm_definer`: a lista fechada continua a mesma (teste da lista de funções e das políticas) |
| Isolamento entre escolas | As três tabelas têm RLS **forçada** (select e insert; update só no documento, e só nas colunas de anulação); a escrita confere que a linha do extrato é da mesma escola. Testes: outra escola recebe 404 ao classificar e lista vazia |
| Só se insere | `balancete_balances` e `pdde_classifications` recusam UPDATE, DELETE e TRUNCATE (gatilhos que valem até para o dono). Corrigir é inserir de novo; o histórico fica na auditoria |
| Documento errado | `pdde_documents` só muda `voided_at`/`voided_by_user_id` (gatilho de colunas imutáveis); nada é apagado |
| Regras no banco, não só na tela | Linha de conta PDDE; repasse é entrada e despesa é saída; documento só em saída; documentos de uma linha nunca somam mais que ela (trava por linha contra dois ao mesmo tempo); chave de NF-e com 44 dígitos e uma NF-e só comprova uma linha |
| Funções de gatilho | `REVOKE ALL ... FROM PUBLIC` (um teste da lista de funções pegou a falta na primeira versão) |
| Valores | Centavos inteiros, com teto; o saldo "em banco" é o que sobra do total, nunca digitado duas vezes |
| Auditoria | Gatilho de auditoria nas três tabelas; textos livres (objeto, observação, fornecedor, chave, número) entram **só pelo nome da coluna**, nunca o conteúdo |
| Planilha | Textos que começam com `=`, `+`, `-`, `@` ganham apóstrofo; o valor em dinheiro nunca (é número) |
| Dados pessoais | O balancete e o relatório do PDDE só têm propósitos, totais, fornecedores e histórico do banco; sem CPF. No extrato em PDF, a linha de detalhe do Pix (hora, CPF, nome) entra no texto da linha **com CPF e CNPJ mascarados**. Medido num extrato real de 439 lançamentos: 0 CPF/CNPJ crus guardados |
| Permissões | `/pdde/*`: `reconciliation:manage`; gravar saldos do balancete: `months:close`; ler o balancete: `reports:read` ou `reports:read_aggregate`. Teste de cada rota para cada papel |

## Achados e o que fiz
| # | Achado | Gravidade | Situação |
|---|---|---|---|
| 1 | O leitor de PDF lia as linhas "Saldo Anterior" e "Saldo" como entradas (R$ 168 mil falsos num extrato real) | Alta (funcional) | **Corrigido** (9ea8779); o saldo final do banco só é guardado quando abertura + linhas = saldo final |
| 2 | Funções de gatilho novas sem `REVOKE ... FROM PUBLIC` | Média | **Corrigido** antes de entrar |
| 3 | A lista da tela sumia por um instante ao salvar (recarregava sem manter o que estava na tela) | Baixa (usabilidade) | **Corrigido** |
| 4 | **O livro caixa parte de zero.** O saldo de quando a escola começou a usar o sistema entra no balancete (tabela nova), mas **não** no resumo nem no fechamento: a "diferença do banco" do fechamento (banco menos caixa) vai mostrar esse valor até o fechamento aprender sobre ele | Funcional, alta para escola com saldo | **Em aberto, decisão de produto**: o caminho limpo é um lançamento de abertura no razão (muda o esquema protegido e exige revisão) |
| 5 | O objeto da despesa do PDDE é texto livre: as categorias oficiais do BB Gestão Ágil estão em portarias que pedem login | Funcional | **Em aberto**: com as portarias vira lista |
| 6 | Leitura de PDF roda no processo da API (um PDF montado de má-fé gasta CPU); só quem tem permissão de conciliação envia | Baixa a média | **Em aberto** (já estava no M4-M7, item 5) |
| 7 | O relatório do PDDE é um espelho: **não envia nada** ao banco nem ao governo | Informativo | A prestação oficial é feita no BB Gestão Ágil e pela prefeitura |
| 8 | Uma despesa do PDDE estornada: o tipo "estorno ou devolução" só marca a linha, não abate o programa | Funcional | **Em aberto** |

## O que NÃO foi testado
Produção (banco real, Dokploy, domínio), carga, restauração de backup, o leitor com OFX e CSV reais (só o PDF
de julho do Banco do Brasil foi usado), o PDF de agosto (é imagem e o leitor recusa de propósito).
