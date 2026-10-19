# M8. PDDE: plano detalhado (rascunho para revisão)

Escrito em 2026-10-15. **Sem código.** Marcado como **[CONFIRMADO]** o que está nos documentos oficiais lidos, **[SUPOSIÇÃO]** o que eu deduzi e **[ABERTO]** o que só as respostas da APM resolvem.

## 0. Estado em 19/10/2026: construído (migração 0028) e o que mudou desde o rascunho

**Entregue (local, aguardando revisão):** a Opção A, a camada de classificação por cima das linhas do extrato da conta de finalidade PDDE. Tabelas `pdde_classifications` (só insere; vale a última decisão) e `pdde_documents` (anula, nunca apaga; os documentos de uma linha nunca somam mais que ela), API em `/schools/{id}/pdde/*` (`lines`, `summary`, classificar, documento, anular, `report.csv` e `report.pdf`), tela "PDDE" no painel e avisos. Usa a permissão `reconciliation:manage` (quem cuida das contas classifica as linhas), não uma nova.

**Correções ao rascunho abaixo (fontes oficiais lidas em 19/10):**
- A Resolução CD/FNDE 17/2024 (Equidade) foi **revogada pela Resolução 8/2026** (7/5/2026, art. 18, IV). Os eixos são SRM, Água/Campo/Agroecologia e Diversidades; a prestação continua igual (art. 13: a UEx classifica o extrato no BB Gestão Ágil; a prefeitura julga no SiGPC). O carimbo "Pagos com recursos do PDDE Equidade", seguido do nome do eixo, está no art. 12, IV, f.
- **Básico (Res. 15/2021, lida):** usos do art. 4º (material permanente, pequenos reparos, material de consumo, avaliação de aprendizagem, projeto pedagógico, atividades educacionais); **vedado** tarifa bancária, pessoal, aluguel/telefone/água/luz e tributos que não incidam sobre a compra (art. 4º, § 2º); conta isenta de tarifas (art. 16, § 2º); duas parcelas (até 30/04 e 30/09); rendimentos voltam ao programa (art. 18, § 3º); prestação à prefeitura até 30/04 do ano seguinte, com demonstrativo, extratos, **conciliação bancária do saldo de 31/12**, cópias "Confere com o original" e atas (arts. 32 e 33); originais guardados por 5 anos após a aprovação (art. 28); parecer "aprovada com ressalva" quando custeio é usado em capital ou o contrário (art. 33, § 4º, b).
- **Qualidade:** é o PDDE Mais Qualidade (Res. 17/2025), só para escolas selecionadas, nos moldes da 15/2021. **Educação Conectada:** Res. 9/2018, plano de aplicação com itens de custeio e capital, parcela única, rendimentos no programa.
- A APM recebe Básico, Equidade, Qualidade e Conectado (resposta de 19/10).

**Decisões tomadas (sem poder perguntar):** os programas são uma lista fixa de quatro mais "Outro programa" com nome livre; o **objeto** da despesa é texto livre (as portarias de categorias do BB Gestão Ágil pedem login e não foram lidas, então o sistema não finge conhecê-las); os repasses podem dizer se são custeio ou capital, e o gasto acima do recebido em uma categoria avisa; a tarifa bancária na conta do PDDE e a falta do extrato de dezembro avisam; o prazo de 30/04 é o da lei, mas a prefeitura define o da escola.

**Não fez / aberto:** o objeto em lista oficial (precisa das portarias); estorno de uma despesa já classificada (REFUND só marca a linha); conferir o texto do carimbo em PDF anexado (não há OCR); ligar a despesa lançada no sistema à classificação (M8e).

## 1. Fontes lidas
- Resolução CD/FNDE nº 17/2024 (PDDE Equidade): `fnde_modelooficial.pdf` na raiz do repositório.
- Manual do BB Gestão Ágil, PDDE e Ações Integradas, FNDE, 1ª edição, outubro de 2024.
- **Não lidas ainda:** Resolução CD/FNDE nº 15/2021 (PDDE Básico) e as portarias de categorias do BB Gestão Ágil (página do FNDE exige login).

## 2. O que a prestação de contas é, de fato
**[CONFIRMADO]** A comprovação do PDDE é feita **classificando cada lançamento do extrato** da conta específica do programa e registrando o documento da despesa. Em ordem, na tela do BB Gestão Ágil:

1. Categoria = o **programa ou ação** (PDDE Básico, Água, Campo, Equidade etc.).
2. 1ª subcategoria = **Custeio** ou **Capital**.
3. 2ª subcategoria = o **objeto** da despesa, de uma lista da resolução de cada programa, mais 4 itens fixos: imposto recolhido direto à prefeitura, estorno ou devolução, despesa não elegível, saldo executado nos objetivos do PDDE Básico.
4. **Documento de despesa:** NF-e pela chave de acesso, ou outro documento com dados à mão.
5. Observação (só a APM vê).

A linha fica **pendente** até os documentos cobrirem o valor (parcial se cobrirem menos). **[CONFIRMADO]** A prefeitura ou secretaria (EEx) analisa e registra o resumo no SiGPC; prazo até 30/04 do ano seguinte.

## 3. A decisão que muda tudo: o razão não precisa ser tocado
O plano antigo previa uma "carteira" dentro dos lançamentos (razão), o que mexe numa parte protegida. Pelo que a prestação é, **isso não é necessário**:

- A prestação trabalha em cima de **linhas do extrato bancário da conta PDDE**, que o M5 a M7 já importam (`bank_statement_lines`).
- Então o PDDE vira uma **camada de classificação por cima das linhas do extrato**, sem alterar `financial_transactions`.
- **[SUPOSIÇÃO]** O caixa próprio da APM (Livro Caixa, fechamento) **continua sem o PDDE**, o que é o desejado: dinheiro do governo fora do caixa comum.

**Opção A (recomendada):** só a camada de classificação. Zero risco ao razão, migração simples.
**Opção B:** carteira dentro do razão. Só se a APM quiser ver o PDDE no mesmo livro. Exige revisão de segurança. Não recomendo para o MVP.

## 4. Modelo de dados proposto (Opção A)
Tudo com `organization_id` e `school_id`, RLS e auditoria, como as tabelas do M5.

| Tabela | Para quê | Observação |
|---|---|---|
| `pdde_objects` | Catálogo: programa, Custeio ou Capital, objeto, portaria de origem, vigência | Dados de referência, alimentados pelas portarias do FNDE. Mudam com o tempo |
| `pdde_classifications` | Uma linha do extrato classificada: programa, Custeio ou Capital, objeto, observação, quem e quando | Uma por linha. Pode ser corrigida antes de a prestação ser dada por enviada |
| `pdde_documents` | Documentos de uma classificação: tipo (NF-e ou outro), chave de 44 dígitos, número, data, valor, fornecedor, anexo | Vários por linha (prestação parcial) |

- **Status por linha, calculado:** pendente (sem classificação ou sem documento), parcial (documentos somam menos que a linha), concluída.
- **Linhas de crédito** (repasses): classificadas só por programa, para o saldo.
- **Saldo por programa e por Custeio e Capital:** repasses menos despesas classificadas.
- **Conta PDDE:** a conta bancária já existe com finalidade "PDDE" (M5). Só ela entra nesta camada.
- **Anexos:** reutilizar o armazenamento de anexos das despesas. **[ABERTO]** se a APM também lança essas despesas no sistema (fluxo de aprovação) ou só classifica no extrato.

## 5. Telas
1. **PDDE, lista do mês:** o extrato da conta PDDE, mês a mês, com o ícone de pendente ou concluída em cada linha (igual ao BB Gestão Ágil).
2. **Classificar uma linha:** três caixas de seleção em cascata (programa, Custeio ou Capital, objeto) e o campo de documento (chave da NF-e, 44 dígitos, ou dados à mão).
3. **Painel do PDDE:** saldo por programa, por Custeio e por Capital, e o número de pendências.
4. **Conferência do carimbo:** aviso ao anexar nota de despesa PDDE para conferir a expressão "Pagos com recursos do PDDE EQUIDADE" + nome do programa (Resolução 17/2024, art. 12, IV, e). **[CONFIRMADO]** vale para o Equidade; para o Básico, **[ABERTO]**.

## 6. Relatório final: o "espelho" da tela do banco
Como o BB Gestão Ágil não tem integração pública conhecida, o relatório sai **na ordem da tela**: por linha do extrato, data, valor, programa, Custeio ou Capital, objeto, documento e observação. A pessoa copia para a tela do banco. Formatos: PDF e planilha. Também uma **lista de pendências** por mês. Isso encerra a decisão "PDF idêntico ou relatório na ordem do sistema": **relatório na ordem da tela** (decisão #9 do plano).

## 7. Regras conhecidas que o sistema pode checar
- **[CONFIRMADO]** PDDE SRM e PDDE Água: 80% Capital e 20% Custeio. PDDE Diversidades: 20% Capital e 80% Custeio (Res. 17/2024). Aviso quando o gasto classificado fugir da proporção.
- **[CONFIRMADO]** Objetos elegíveis por programa (Anexo III da Res. 17/2024): vão para o catálogo.
- **[CONFIRMADO]** "Despesa não elegível" é um item permitido: o sistema avisa, não bloqueia.
- **[ABERTO]** Prazos e proporções do PDDE Básico (Res. 15/2021).

## 8. Divisão em entregas
| Parte | O que entrega | Depende de |
|---|---|---|
| **M8a** | Descoberta (este documento) | respostas da APM |
| **M8b** | Migração 0020 (3 tabelas), catálogo dos objetos, tela de lista e de classificação | portarias de categorias (PDFs) |
| **M8c** | Documentos da despesa (NF-e e outros), status pendente, parcial, concluída, observação | M8b |
| **M8d** | Painel de saldos, espelho em PDF e planilha, lista de pendências | M8c |
| **M8e** (opcional) | Ligar a despesa lançada no sistema à classificação, conferir o carimbo | decisão sobre o fluxo |

Segurança: nova tabela com permissão própria `pdde:manage` (só gestão), RLS por escola, auditoria e sem apagar. Revisão independente fica no M9.

## 9. Perguntas abertas (as que a APM vai responder)
1. Qual sistema a APM usa hoje: BB Gestão Ágil, SIGPC Ágil, ou só manda documentos à prefeitura (Res. 15/2021, art. 33)?
2. Quais programas recebe (Básico, Equidade, outros)?
3. Quem faz a prestação e quem na prefeitura registra no SiGPC?
4. Quanto recebe por ano e em quantas parcelas.
5. Papel do contador hoje.
6. Lista oficial de categorias (portarias do BB Gestão Ágil) e um print da tela de classificação.
7. Um extrato do Banco do Brasil da conta do PDDE (dados trocados).
8. A APM lança as despesas do PDDE também no sistema (com aprovação), ou só classifica o extrato?

## 10. O que eu não vou fazer
- Enviar dados ao governo ou ao Banco do Brasil. Não há integração conhecida.
- Afirmar quais categorias valem sem as portarias.
- Mexer no razão sem decisão sua (Opção B).
