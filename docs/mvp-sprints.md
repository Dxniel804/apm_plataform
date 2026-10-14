# MVP do APM Digital: plano de sprints

Atualizado em 2026-10-14. **Proposta para aprovação do dono. Nada deste plano foi iniciado**: a seção 0 de `docs/arquiteturasystemforklin.md` manda aprovar a ordem antes de implementar.

Base: `docs/thelastversion.md`, `docs/arquiteturasystemforklin.md`, as decisões da conversa de 14/10 e o código verificado no mesmo dia. Etiquetas, como no documento da arquitetura: **[HOJE]** existe e foi verificado, **[PLANEJADO]** foi desenhado e não existe, **[ABERTO]** depende de decisão do dono.

## 1. Regras que valem para todos os sprints

1. **R1. O dinheiro das contribuições vai direto para a conta da APM e nunca passa por conta da Forklin.** Decisão do dono, 14/10. Ela filtra a escolha do gateway (sprint G).
2. **R2. O gateway fica em espera.** O MVP é construído "pronto para split e tarifas" sobre o provedor de teste que já existe.
3. **R3. Só Pix.** Boleto, cartão, cobrança recorrente de verdade e rifas ficam fora.
4. **R4. Login próprio, sem SSO**, até o dono decidir o contrário (padrão da seção 11.1).
5. **R5. Sem papel `accountant`.** A gestão baixa o "pacote do mês" (padrão da seção 11.6).
6. **R6. O navegador nunca decide estado financeiro.** Nenhuma regra financeira no front.
7. **R7. Execução.** Uma branch por sprint. `git add` só com lista de arquivos, conferida com `git show --stat`. Push só com um "pode subir" novo. O banco demo não é alterado além do que foi autorizado.
8. **R8. Pronto, em todo sprint:** migração com subida e descida testadas (`test_migration_cycle`); testes novos; API com `pytest`, `ruff`, `mypy` strict e `app.posture`; web com `tsc`, `lint`, `vitest` e `build`; e2e Playwright com axe em 320, 360 e desktop, contra banco descartável; teste de isolamento entre escolas em toda rota nova; documento em `docs/`; conferência manual em 1440, 820 e 390 px.

## 2. Premissas assumidas (corrija o que estiver errado)

| # | Premissa | Origem |
|---|---|---|
| 1 | "Contribuição Mensal" é o fluxo avulso de hoje, com **mês de referência** | padrão 11.4 |
| 2 | Inadimplência vira **meta e adesão** (sem cadastro de famílias) | padrão 11.5 |
| 3 | Custo é **por produto**; entrega é **por pedido**, marcada só pela gestão | dono, 14/10 + padrão |
| 4 | Rifas **fora** do MVP | dono, 14/10 |
| 5 | Um único "Despesas" no menu, dentro de "Lançamentos do mês" | dono, 14/10 |
| 6 | O slug da escola é o do APM e não muda | padrão 11.3 |
| 7 | A verba do PDDE entra numa conta bancária da escola, **separada** | dono, 14/10 |
| 8 | A Fase 2 fiscal (retenções, guias, obrigações) fica **depois** do MVP | proposta, a confirmar |

## 3. Ponto de partida (verificado em 2026-10-14)

- **GitHub:** `main` e `feat/s5-campaigns` em `45a4cec`. S0 a S6 entregues.
- **Working tree:** 41 arquivos modificados, **sem commit** (redesenho v2 do front: tokens, login, portal com abas "Contribuição mensal | Campanhas", menu com um só "Despesas", "Campanhas" no lugar de "Personalização", "Total de saídas"). **Não foi verificado com login real.** Falta trocar `ClosingsArea.tsx:116`, que ainda diz "Saídas pagas". Inclui os arquivos de login do dono.
- **Pix [HOJE]:** só `SandboxPixProvider`; provedor real responde 501; `payment_accounts.provider` aceita só `BB` e `SANDBOX`; o webhook descobre a escola pelo segredo único de cada conta.
- **Já existe [HOJE]:** `school_settings.min_contribution_cents` (padrão R$ 10,00); slug de escola não alterável pela aplicação (migração 0005); tabelas `pix_charges`, `webhook_events` e `audit_logs`. Última migração: 0013.
- **Não existe:** custo de produto, entrega de pedido, campos de tarifa, conta bancária no cadastro da escola, importação de extrato, Livro Caixa, carteiras do PDDE.

## 4. Visão geral

Tamanhos: **P** = poucos arquivos, sem migração. **M** = migração e telas. **G** = vários módulos, migração e segurança. Números de migração são indicativos.

| Sprint | Objetivo | Tam. | Depende de |
|---|---|---|---|
| **M0** | Fechar o redesenho que está na working tree | P | seu OK para os arquivos de login |
| **M1** | Campanhas v2: dashboard, pedidos, entrega, custo, PDF | G | M0 |
| **M2** | Porta de entrada do responsável, link da escola e configurações | M | M0 |
| **M3** | Dashboard com dados reais e "meta e adesão" | M | M2 |
| **M4** | Pagamentos prontos para split e tarifas (sem gateway) | G | decisão de quem paga a taxa |
| **M5** | Conciliação I: contas bancárias e importar OFX | G | extrato OFX real (para validar) |
| **M6** | Conciliação II: ações, fechamento, Livro Caixa e pacote do mês | M | M5 |
| **M7** | Conciliação III: CSV e PDF | M | M5, extratos reais |
| **M8** | PDDE: carteiras Custeio e Capital e relatórios | G | modelos oficiais do FNDE |
| **M9** | Endurecimento e pronto para produção | M | M4, M5, M6 |
| **G** | Gateway real (**em espera**) | G | escolha do gateway |

Ordem proposta: M0, M1, M2, M3, M4, M5, M6, M7, M8, M9. **G entra assim que o gateway for escolhido** e pode andar em paralelo a M5 em diante. **Produção só depois de G e M9.**

## 5. Sprints

### M0. Fechar o redesenho (P)
- Rodar a verificação completa sobre a working tree: `eslint`, `tsc`, `vitest`, `next build` e e2e. **Não rodar `next build` com o `next dev` no ar** (deixa o CSS velho).
- Trocar "Saídas pagas" por "Total de saídas" em `ClosingsArea.tsx` e nos testes e e2e que citam.
- Conferir as telas com login real (senha da demo em `.maestri/private/dev-seed-password.txt`, usada sem imprimir).
- Passar "Alterar senha" de página para janela (`FormModal`).
- Commits por tema, com lista de arquivos. Os arquivos de login só entram com o seu OK.
- Fora: "Lembrar de mim", "Esqueci minha senha" e "Evolução do caixa" (não há API; recuperação de senha precisa de e-mail real, ver M9).

### M1. Campanhas v2 (G)
**Objetivo:** a gestão acompanha cada campanha: quanto entrou, quanto custou, quem comprou e o que falta entregar.
- Migração 0014:
  - `campaign_items.unit_cost_cents` (nulo permitido, não negativo);
  - `contribution_items.unit_cost_cents`, **cópia imutável do custo na hora da compra**, com a mesma regra de banco que já protege o preço;
  - flag `campaigns.ask_student_class` (padrão ligado): pede aluno e turma no pedido, para a gestão saber a quem entregar;
  - entrega por pedido: estado `PENDING`/`DELIVERED`, quem marcou e quando, **só para pedido pago**, reversível com registro em `audit_logs`.
- API (permissão `campaigns:manage`): resumo da campanha (arrecadado, custos, lucro, vendidos por produto, pedidos por situação de pagamento e de entrega); lista de pedidos com filtro e busca; marcar e desmarcar entrega, inclusive em lote; PDF da campanha pelo `reports/layout.py`.
- Situação de pagamento no painel: `PENDING` = Pendente, `PAID` = Aprovado, `CANCELLED`/`EXPIRED`/`REJECTED` = Cancelado.
- Web: `/painel/campanhas/{id}` com abas Resumo, Pedidos e Produtos (o editor de hoje). Lucro só aparece se **todos** os itens vendidos tiverem custo; senão mostra "custo não informado".
- O custo é métrica de gestão: **não é lançamento no caixa**. A saída de verdade continua sendo a Despesa.
- Testes: cópia do custo sob concorrência (como o teste da corrida de preço), entrega só em pedido pago, isolamento entre escolas, PDF.
- Fora: entrega por item, avisos ao responsável, custos livres ligados à campanha.

### M2. Porta de entrada e link da escola (M)
- **Contribuição mensal** com mês de referência: coluna `contributions.reference_month` (nula), escolhida no fluxo público e mostrada no extrato e no comprovante. As abas "Contribuição mensal | Campanhas" já existem no código do M0.
- **Painel "Link da escola"**: endereço, botão copiar, QR Code para baixar e cartaz A4 com QR. A biblioteca de QR já está no web.
- **Prévia ao compartilhar** (Instagram, WhatsApp): título, descrição e imagem da página `/escola/{slug}`.
- **Domínio público** pela variável `PUBLIC_BASE_URL`. A decisão do domínio (por exemplo `doar.forklin.com`) é do dono. **Antes de imprimir qualquer QR, o endereço precisa estar fechado.**
- **Slug:** a aplicação já não consegue alterá-lo [HOJE]. Acrescentar teste e documentar que a renomeação é operação da plataforma. Redirecionamento de slug antigo só se a renomeação virar rotina [ABERTO].
- **Configurações da escola** (resolve o item que ficou fora do S5): valores sugeridos, textos da página de valor livre e, para o M3, **meta mensal de arrecadação** e **número esperado de contribuições**.
- Testes: link e QR corretos, página pública sem login, escola inexistente devolve o mesmo 404.

### M3. Dashboard com dados reais (M)
- Implementar os dados do desenho v2 (a parte visual já está no M0). Faltam as séries:
  - API `GET …/statement/series`: entradas, saídas e saldo por mês (6 a 12 meses), **calculados no servidor**;
  - cartão **"Meta e adesão"**: arrecadado do mês contra a meta e contribuições pagas contra as esperadas. O texto diz "contribuições", **não "famílias"**, porque a identificação é opcional e não dá para contar famílias.
- **Pendências** em lista, com dados reais.
- Teste de consistência: o total do gráfico, os indicadores do extrato e o fechamento do mês **batem entre si**.
- Gráficos sem biblioteca nova (SVG como hoje), com tabela de texto como alternativa acessível.
- Fora: inadimplência por pessoa.

### M4. Pagamentos prontos para split e tarifas, sem gateway (G)
**Objetivo:** o sistema sabe registrar e mostrar valor bruto, tarifas e líquido. Quando o gateway chegar, entra só um adaptador.
- **Portão de decisão antes da migração:** quem paga a taxa (A escola, B o responsável, C a Forklin).
- Migração 0016, tabela de detalhe 1:1 com a contribuição Pix: tarifa do gateway, tarifa da plataforma, quem paga, valor cobrado do pagador e líquido da escola. **Gravada no mesmo instante em que o pagamento vira PAGO**, e depois não muda.
- Interface `PixProvider`: a cobrança recebe um **plano de split** (valor da plataforma e destino); `fetch_payment` devolve tarifa e identificador fim a fim. O `SandboxPixProvider` simula tarifa fixa e split.
- **Webhook amarrado pela cobrança**, não pelo segredo da conta. Alternativa preferida: o identificador de correlação que a gente gera carrega a escola **assinada com HMAC**, então a escola vem de um dado nosso e a regra de isolamento (RLS) continua valendo, sem busca entre escolas. Alternativa: rota por conta de pagamento. **Revisão de segurança obrigatória.** Sem função `SECURITY DEFINER` nova.
- **Valor mínimo** `min_contribution_cents` [HOJE] passa a ser validado contra as tarifas, para a escola nunca receber valor negativo ou irrisório.
- Telas e relatórios: entrada bruta, tarifas e líquido no detalhe da contribuição, no extrato, no fechamento e no PDF ("Tarifas de recebimento").
- Documento `docs/payments.md` com o modelo, a regra R1 e os três arranjos de taxa.
- Testes: confirmação repetida (mesmo aviso duas vezes), cruzamento entre escolas, soma bruto − tarifas = líquido, ciclo da migração.
- Perguntas para o **contador** (podem andar em paralelo): como classificar a tarifa da Forklin; bruto e tarifa separados ou só o líquido.

### M5. Conciliação I: contas bancárias e importar OFX (G)
- Migração 0017:
  - `bank_accounts` por escola (apelido, banco, final da conta, **finalidade: geral ou PDDE**, ativa). Uma escola pode ter **mais de uma conta**;
  - `bank_statement_imports` (conta, período, `sha256` para barrar reenvio, saldo inicial e final, quem subiu);
  - `bank_statement_lines` (data, valor com sinal, texto minimizado, identificador do banco, identificador fim a fim do Pix, estado do pareamento).
- Leitor de OFX 1.x (SGML) e 2.x (XML), seguro: tamanho limitado, sem entidades externas, nada do arquivo é executado.
- **Motor de pareamento** (função pura, determinística): identificador fim a fim do Pix, depois valor e data (janela de poucos dias úteis), depois texto de tarifa; um-para-um; **ambíguo vira "revisar", nunca adivinha**.
- Privacidade: **não guardar o arquivo original**, só o hash; mascarar CPF e CNPJ do texto; definir retenção.
- Permissão `reconciliation:manage`. Tela `/painel/conciliacao` só de leitura: Conferidos, Faltam no sistema, Faltam no extrato e Divergências.
- Desenvolvimento com arquivos sintéticos feitos pela especificação. **Preciso de um OFX real do banco da escola para validar** (nomes e CPFs trocados).
- Encaixe futuro: o extrato do gateway entra como outra fonte do mesmo motor (sprint G).

### M6. Conciliação II: ações, fechamento, Livro Caixa e pacote do mês (M)
- Ações por linha, sempre confirmadas pela gestão: Pix direto, entrada por TED ou depósito, despesa de tarifa, abrir despesa já preenchida, ou **ignorar com motivo obrigatório** (auditado). Todas idempotentes.
- O saldo final do extrato **preenche** o "saldo informado pelo banco" do fechamento. A diferença continua calculada pelo banco e **fora do hash** do fechamento.
- **Livro Caixa**: relatório cronológico com saldo corrente, por conta e por período, em PDF e CSV [PLANEJADO]. Deriva do razão, não é um segundo caderno.
- **Pacote do mês**, baixado pela gestão: PDF do extrato com a conciliação (com data e hora de geração), CSV dos lançamentos e anexos das despesas.
- Fora: papel `accountant`, e-mail automático (não há e-mail real).

### M7. Conciliação III: CSV e PDF (M)
- **CSV:** perfis de mapeamento por banco (colunas, formato de data, vírgula decimal, sinal do débito), escolhidos uma vez por escola. Usa o motor do M5.
- **PDF (melhor esforço):** `pypdf` e, para PDF escaneado, o serviço de OCR. **Toda linha vinda de PDF exige revisão** antes de virar lançamento.
- Limites de tamanho e de linhas, taxa de envio e retenção.
- Precisa de 1 CSV e 1 PDF reais.

### M8. PDDE (G, em duas partes)
Verba do governo federal, separada do caixa comum. [ABERTO] até chegarem os documentos.
- **M8a: descoberta (sem código).** Receber do dono os modelos vigentes, a resolução do FNDE e uma prestação já feita. **A prestação é feita no SiGPC (gov.br).** Decidir se o produto gera PDF idêntico ao formulário ou um relatório na ordem em que o SiGPC pede. Confirmar a resolução e o prazo em vigor.
- **M8b: modelo e telas.** Dimensão **"carteira"** (Custeio ou Capital) nos lançamentos, com saldo por carteira; vínculo com a conta bancária do PDDE (M5); regras de classificação das categorias; relação de bens para despesas de Capital.
- **M8c: relatórios** conforme a decisão do M8a.
- Atenção: mexe no razão, que é protegido. Migração com revisão de segurança.

### M9. Endurecimento e pronto para produção (M)
- **Revisão de segurança independente** do S1 (RLS e `SECURITY DEFINER`), do webhook por cobrança (M4) e dos três tipos de arquivo (M5 a M7).
- Decisão do **modelo real de OCR** (spike do dono: 30 fotos e CPU/GPU).
- WebKit (nunca testado).
- LGPD: retenção e anonimização dos dados de famílias e do extrato.
- Recuperação de senha, que **exige e-mail real** [ABERTO].
- Chaves liga/desliga para toda integração nova, ensaio em cópia do banco e backup verificado antes de tocar produção (regra 9 da arquitetura).
- Teste de aceitação com uma escola real. Documentação final.

### G. Gateway real (em espera)
Só começa quando o gateway for escolhido. **Critérios obrigatórios**, na ordem de importância:
1. **R1:** o dinheiro cai em conta da APM (CNPJ próprio) e **não** em saldo da Forklin. Uma "subconta" que seja só saldo virtual dentro da conta da Forklin não serve.
2. Conta criada por API, com onboarding do CNPJ de uma associação sem fins lucrativos.
3. Webhook assinado e identificador fim a fim do Pix no aviso de pagamento.
4. Ambiente de testes que **simule o pagamento**.
5. Preço por Pix compatível com contribuições de R$ 10 a R$ 50.
6. Extrato ou relatório de liquidação por API.
7. Receita da Forklin: split fixo por Pix **ou** mensalidade do produto cobrada pela Central. A segunda opção dispensa split e funciona com qualquer gateway.
- Candidatos e o que já se sabe (documentação, sem teste): **Woovi** (sandbox, webhook assinado e E2E, mais barato; dúvida: subconta parece saldo virtual); **Asaas** (subconta real, mais caro, webhook por token, sandbox sem simular pagamento por API); **Pagar.me** (recebedores reais, Pix com split só para afiliados); **Efí** (não avaliado); **AbacatePay** fora (sem split nem subconta); **Pix direto no Banco do Brasil** (o provedor `BB` já previsto), sem split.
- Entregas: adaptador atrás de `PixProvider`; onboarding das contas das APMs; credenciais só por `secret_ref` em cofre; verificação da assinatura; ensaio de ponta a ponta no sandbox com túnel público para o webhook; validação em produção com **um pagamento real de valor mínimo**, atrás de chave liga/desliga.

## 6. Decisões pendentes

| # | Decisão | Trava | Padrão |
|---|---|---|---|
| 1 | Os arquivos de login entram no commit? | M0 | só com o seu OK |
| 2 | Entrega por pedido ou por item | M1 | por pedido |
| 3 | Aluno e turma obrigatórios nas campanhas | M1 | ligado por campanha |
| 4 | Domínio público do link | M2 | não imprimir QR antes |
| 5 | Redirecionamento de slug antigo | M2 | não construir |
| 6 | **Quem paga a taxa: A, B ou C** | M4 | sem padrão |
| 7 | Tarifa da Forklin: classificação contábil | M4 | pergunta ao contador |
| 8 | Contador humano revisa o que for ao governo? | M6, M8 | sem resposta |
| 9 | PDF idêntico ao FNDE ou relatório para o SiGPC | M8a | decidir com os modelos |
| 10 | Recuperação de senha e e-mail real | M9 | fora do MVP até haver e-mail |
| 11 | **Gateway** | G | em espera |
| 12 | Receita da Forklin: split por Pix ou mensalidade | G | em aberto |
| 13 | SSO com a Central | fora | login próprio |

## 7. O que preciso de você, por sprint

- **M0:** OK para os arquivos de login; rótulo final de "Total de saídas".
- **M1:** respostas 2 e 3 acima.
- **M2:** domínio do link.
- **M4:** quem paga a taxa; respostas do contador.
- **M5:** 1 extrato **OFX** real da escola (nomes e CPFs trocados).
- **M7:** 1 **CSV** e 1 **PDF** reais.
- **M8:** modelos do FNDE vigentes, uma prestação já feita, a resolução em vigor, e confirmar se a conta do PDDE está no CNPJ da APM.
- **G:** escolha do gateway, contas de teste (a chave **só no `.env`**, nunca no chat) e as respostas do suporte.
- **M9:** o spike de OCR e a decisão sobre e-mail.

## 8. Fora do MVP

Rifas. Boleto e cartão. Cobrança recorrente de verdade e cadastro de famílias (inadimplência por pessoa). Papel `accountant` e e-mail automático. Fase 2 fiscal: retenção de INSS, ISS e IRRF, guias DARF e GPS (a "cola de prova" do item D), e obrigações acessórias (DCTF, ECF, ECD, EFD-Reinf, eSocial). Integração com a Central e SSO. Open Finance.

## 9. Riscos

- **Redesenho sem commit (M0):** 41 arquivos misturados. Um erro de `git add` leva coisa que não devia. Por isso a regra R7.
- **Gateway sem produção possível:** sem G não há Pix real. Nada do MVP vai ao ar sem ele.
- **Webhook por cobrança (M4):** é a mudança mais sensível à segurança do plano.
- **Extratos reais:** sem eles o leitor erra nos detalhes de cada banco (M5 e M7).
- **PDDE:** regra e sistema do FNDE mudam. Confirmar a norma vigente antes de construir.
- **Tributação:** a "isenção de bitributação" do desenho de pagamentos não foi verificada. Depende do arranjo escolhido em G e do contador.
