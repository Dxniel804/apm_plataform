# Escopo e Atualizações - Sistema APM Digital (Última Versão)

## 1. Módulo de Campanhas (Antiga tela de "Personalização")
- **Alteração de Nomenclatura:** A aba "Personalização" deve ser renomeada para "Campanhas".
- **Dashboard Específico:** Como a escola pode ter múltiplas campanhas ativas simultaneamente (ex: Xícara de Dia dos Pais, Árvore de Natal), a visualização principal deve listar as campanhas. Ao clicar em uma campanha específica, o usuário deve ter acesso a uma dashboard dedicada a ela.
- **Métricas e Relatórios:** A página da campanha deve exibir dados como: total arrecadado, custos, quantidade vendida, etc. Deve haver uma opção para **Exportar em PDF**.
- **Gestão de Entregas e Pagamentos:** É necessário um painel em formato de lista (tabela) dentro da campanha contendo: 
  - Nome do comprador.
  - Produto adquirido.
  - Status do pagamento (Pendente, Aprovado, Cancelado).
  - Status de entrega (Pendente, Entregue).
- **Objetivo:** Fornecer à gestão uma visão ampla e organizada das entradas e saídas financeiras de cada campanha, facilitando a logística de entrega dos produtos.

## 2. Visão do Responsável (UI/UX)
- **Tela "Contribuir com a APM":** A interface para os pais/responsáveis precisa ser otimizada. Deve apresentar dois botões (ou cards) principais e claros:
  1. **Contribuição Mensal:** Direciona para o pagamento da mensalidade/taxa recorrente.
  2. **Campanhas:** Direciona para a vitrine de produtos ou eventos sazonais da escola.

## 3. Lançamentos do Mês e Sidebar
- **Correção de Redundância:** Ao clicar na rota "Lançamentos do mês" na barra lateral (sidebar), o submenu "Despesas" está aparecendo de forma duplicada na tela. É necessário revisar a estrutura de navegação e a UI para evitar repetições.

## 4. Dashboard Principal
- **Revisão de Métricas:** O termo "Saídas pagas" está confuso. É preciso um estudo de usabilidade para definir os melhores nomes para as métricas financeiras (ex: "Despesas Quitadas" ou "Total de Saídas").
- **Gráficos:** Os gráficos precisam ser funcionais, dinâmicos e refletir os dados reais de fluxo de caixa (entradas vs. saídas) e inadimplência de forma clara.

## 5. Novas Funcionalidades e Integrações
- **Gateway de Pagamento:** Integrar nativamente um gateway de pagamento (ex: Asaas, Mercado Pago, Pagar.me ou Stripe) para gerar Pix, boletos e aceitar cartão de crédito. Isso automatizará a mudança de status de pagamentos de "Pendente" para "Aprovado" via Webhooks nas Campanhas e Contribuições Mensais.
- **Módulo de Rifas:** Dentro da seção "Campanhas", adicionar a possibilidade de criação e gestão de Rifas digitais. O sistema deve gerar números virtuais e reservá-los automaticamente assim que o pagamento for aprovado pelo Gateway.

---

# Módulo de Contabilidade Automatizada (Substituição de Contador)

Este módulo é o diferencial do sistema, com o objetivo de automatizar as rotinas fiscais e financeiras de uma Associação de Pais e Mestres (ONG/Sem fins lucrativos), eliminando a necessidade de contabilidade terceirizada. A implementação deve ser faseada.

### FASE 1: MVP (Prioridade Máxima)
Resolver essas duas áreas iniciais atende 80% das dores diárias da gestão escolar.

**A. Gestão de Caixa e Conciliação Bancária (Baixa Complexidade)**
**Objetivo:** Automatizar o Livro Caixa da APM.
*   **Importação de Dados:** O sistema deve permitir o upload de extratos bancários no formato `OFX` (ou integração via Open Finance/API bancária).
*   **Conciliação:** O sistema deve cruzar as linhas do extrato bancário com as contas a pagar/receber registradas no sistema (Lançamentos).
*   **Categorização:** O usuário apenas confirmará a categoria de cada despesa (ex: "Manutenção", "Papelaria").
*   **Output:** Geração automática do relatório de **Livro Caixa** padrão, consolidando entradas, saídas e saldo do período.

**B. Relatórios de Prestação de Contas do PDDE (Baixa Complexidade)**
**Objetivo:** Automatizar a prestação de contas do Programa Dinheiro Direto na Escola (verba do Governo Federal).
*   **Separação de Carteiras:** O sistema deve tratar a verba do PDDE em "carteiras digitais" separadas do caixa comum da APM, dividindo o saldo estritamente entre **Custeio** (materiais de consumo) e **Capital** (bens duráveis/equipamentos).
*   **Templates Estritos:** Geração automática de relatórios em **PDF** que repliquem exatamente o layout, as tabelas e os formulários exigidos pelo FNDE (Fundo Nacional de Desenvolvimento da Educação).
*   **Output:** Formulários preenchidos automaticamente com os dados das notas fiscais e fornecedores, prontos para impressão e assinatura da diretoria.

### FASE 2: Expansão Tributária e Fiscal
A ser implementada após a consolidação do MVP.

**C. Motor de Cálculos de Retenção de Impostos (Média Complexidade)**
**Objetivo:** Calcular os impostos retidos na fonte quando a APM contrata serviços de terceiros.
*   **Regra de Negócio (Lançamento de Despesa):** Ao registrar o pagamento de um serviço, o sistema deve solicitar o documento do prestador (CPF ou CNPJ).
*   **Cálculo Automático:** Com base no tipo de serviço e no valor bruto, o sistema aplicará as alíquotas vigentes para calcular os descontos de **INSS, ISS e IRRF**.
*   **Desmembramento Financeiro:** O sistema dividirá a despesa em duas saídas de caixa: Valor Líquido (pago ao prestador) e Valor Retido (pago ao Governo).

**D. Gerador de Guias de Pagamento - DARF/GPS (Média a Alta Complexidade)**
**Objetivo:** Facilitar o pagamento dos impostos retidos.
*   **Geração:** O sistema deve compilar os valores retidos no mês e você não gera o código de barras. Seu sistema vai entregar os dados mastigados, como uma "cola de prova". A tela vai mostrar:
"Atenção: Você precisa pagar o imposto da nota fiscal do Pintor.
Valor: R$ 300,00*
Código do Imposto: 1708*
Vencimento: 20/11/2026*
[ CLIQUE AQUI PARA ABRIR O SITE DA RECEITA ]"*
A diretora clica, o site público do governo abre, e ela só copia e cola os números que o seu sistema deu. Isso já resolve 90% da dor (que é calcular o imposto corretamente) sem você precisar programar integrações complexas no primeiro dia.

**E. Gerador de Arquivos do Governo - Obrigações Acessórias (Alta Complexidade)**
**Objetivo:** Substituir a entrega das declarações contábeis e fiscais da APM.
*   **Formatos de Exportação:** Processar os dados financeiros do ano e compilar arquivos estruturados (`.TXT` ou `.XML`) seguindo rigorosamente os layouts da Receita Federal.
*   **Declarações Abrangidas:** DCTF, ECF, ECD, EFD-Reinf e eSocial.
*   **Fluxo de Usuário:** O usuário baixa o arquivo do sistema e faz a importação direta nos programas validadores da Receita.