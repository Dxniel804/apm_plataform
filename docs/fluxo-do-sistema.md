# APM Digital: o fluxo do sistema, de ponta a ponta

Guia de leitura para quem não programa. Cada seção responde a uma pergunta: **quem faz o quê, em qual tela e em qual rota da API**. Atualizado em 19/10/2026 (migrações até a 0030).

> Como ler as rotas: o caminho `/schools/{s}/...` significa "da escola `s`" (a API confere que é a escola da pessoa logada). Todas começam com `/api/v1`. "Quem" é o que a pessoa precisa poder fazer; no dia a dia só existem dois cargos (abaixo).

---

## 1. O que é, em uma frase
Um **caixa digital da APM (associação de pais e mestres)**: as famílias contribuem por um link público, a secretaria controla o dinheiro (despesas, fechamento do mês, conferência com o banco), e o sistema prepara os **relatórios e formulários** que a escola precisa entregar, inclusive os do **PDDE** (dinheiro federal).

**Ele nunca mexe no dinheiro de verdade.** Quem paga é o banco; o sistema **registra e confere**. Também não envia nada ao governo: ele deixa tudo pronto para a escola copiar ou entregar.

## 2. Quem usa
| Quem | Tem login? | O que faz |
|---|---|---|
| **Secretaria** | sim | Cuida de tudo: aprova e paga despesas, fecha o mês, concilia o banco, faz campanhas, PDDE, impostos, convida pessoas. Não pede despesa para si mesma (quem aprova não escreve). |
| **Funcionário** (`staff`) | sim | Só pede despesas (e acompanha as suas) e faz pedidos à secretaria (ex.: "troquem a lâmpada"). |
| **Família** (responsável) | **não** | Contribui pelo link público da escola, sem criar conta. Recebe um comprovante. |

Cada pessoa pertence a **uma escola** e só enxerga os dados dela (isolamento garantido no banco, não só na tela).

## 3. Mapa das telas
**Públicas** (sem login):
| Tela | Para quê |
|---|---|
| `/` | Manda para o login. |
| `/escola` | A família digita o código da escola. |
| `/escola/{código}` | A página de contribuição da escola (valores sugeridos, campos, Pix). |
| `/escola/{código}/campanha/{id}` | A família escolhe produtos de uma campanha e paga. |
| `/escola/{código}/pedido/{token}` | Comprovante do pagamento (o token é o "segredo" do link). |
| `/login`, `/esqueci-senha`, `/redefinir-senha` | Entrar e recuperar a senha por e-mail. |
| `/accept-invitation` | Quem foi convidado escolhe a senha. |
| `/sso/start`, `/sso/callback` | "Entrar com Forklin" (só quando a integração está ligada). |

**Painel** (com login, `/painel/...`):
| Tela | Quem | Para quê |
|---|---|---|
| `/painel` | secretaria | Dashboard do mês: entradas, saídas, saldo, meta e adesão, gráfico. |
| `/painel/despesas` | os dois | Secretaria: fila de aprovação e pagamento. Funcionário: "minhas despesas". |
| `/painel/solicitacoes` | os dois | Pedidos do funcionário à secretaria. |
| `/painel/campanhas` (e `/{id}`) | secretaria | Vendas da escola (festa, camiseta): produtos, pedidos, entrega, relatório. |
| `/painel/fechamento` | secretaria | Fechar o mês, Livro Caixa, relatórios, pacote do mês e o **Balancete**. |
| `/painel/conciliacao` | secretaria | Contas do banco, importar extrato e comparar com o livro. |
| `/painel/pdde` | secretaria | Prestação do dinheiro federal: classificar linhas, documentos e **formulários do FNDE**. |
| `/painel/impostos` | secretaria | Regras de imposto, retenções e a "cola" para pagar. |
| `/painel/equipe` | secretaria | Convidar, suspender e reativar pessoas. |
| `/painel/configuracoes` | secretaria | Nome e endereço do link, valores sugeridos, metas, QR code e cartaz. |
| `/painel/conta` | os dois | Trocar a própria senha. |

---

## 4. Os fluxos, passo a passo

### A. A família contribui (a entrada de dinheiro)
1. A família abre o link da escola (QR code do cartaz ou Instagram), escolhe o valor e preenche os dados. → `GET /public/schools/{slug}` (valores e campos) e `POST /public/schools/{slug}/contributions`.
2. O sistema cria a contribuição **"aguardando pagamento"** e uma cobrança Pix. A página consulta o estado de tempos em tempos. → `GET .../contributions/{token}/charge`. Se a cobrança vencer: `POST .../charges` cria outra.
3. O banco avisa que foi pago. → `POST /webhooks/pix/{provedor}`. **O sistema não confia no aviso**: pergunta ao provedor o que aconteceu antes de marcar como pago. Se o valor pago for diferente, a contribuição vai para **"em revisão"** e a secretaria decide.
4. Pago: a família vê o comprovante. → `GET .../contributions/{token}/receipt`.
5. Contribuições em dinheiro, transferência ou Pix direto na conta são **registradas pela secretaria**: `POST /schools/{s}/contributions` (dinheiro/transferência) ou pela Conciliação (Pix direto).

> **Em produção hoje, o Pix real está desligado** (`PIX_LIVE_ENABLED=false`): a página responde "pagamentos pausados" até o gateway (Pagar.me) ser integrado. O resto do sistema funciona.

### B. Campanhas (vendas da escola)
Secretaria cria uma campanha (**rascunho**), cadastra produtos (nome, preço, limite por pedido, foto), **ativa** (precisa de pelo menos um produto) e acompanha pedidos, pagamento e **entrega**. Encerrar é definitivo. Mudar um preço depois **nunca altera pedido já feito**. Rotas em `/schools/{s}/campaigns/...` (criar, editar, ativar, encerrar, produtos, imagens, painel, pedidos, marcar entrega, PDF). A família compra por `/public/schools/{slug}/campaigns/...`.

### C. Despesa: do pedido ao pagamento
1. **Funcionário** cria a despesa (**rascunho**), anexa a nota e **envia**. → `POST /expenses`, `.../attachments`, `.../submit`. A leitura automática da foto da nota (OCR) só **sugere** campos e fica desligada por padrão.
2. **Secretaria** decide (nunca da própria despesa): **aprova** (pode aprovar valor menor se o funcionário pagou do bolso), **rejeita** (final, com motivo) ou **pede correção**. → `.../approve`, `.../reject`, `.../request-correction`.
3. Depois de aprovada:
   - **A APM pagou** (Pix, boleto): secretaria registra o pagamento. → `.../pay`.
   - **O funcionário pagou do bolso**: secretaria registra o **reembolso** feito no banco. → `.../reimburse`.
4. Cancelar: o autor cancela rascunho/correção; quem aprova pode cancelar uma aprovada.

Estados de uma despesa: rascunho → enviada → (correção pedida ↔ enviada) → aprovada → paga · ou rejeitada · ou cancelada.

### D. Pedidos do funcionário
Funcionário abre um pedido (com fotos). Secretaria **assume** (em andamento) e **resolve** com uma nota. O autor pode retirar enquanto aberto. → `/schools/{s}/requests/...`.

### E. O mês: extrato, fechamento e relatórios
- **Extrato do mês** (todas as entradas e saídas com o saldo após cada uma), **resumo** (dois saldos: em caixa e após reembolsos pendentes), **pendências** (o que ainda não entrou no saldo), **série** (gráfico) e **meta e adesão**. → `/schools/{s}/statement...`.
- **Fechar o mês**: a secretaria fecha **em ordem** (não dá para fechar outubro sem setembro) e só depois de o mês terminar. O banco de dados calcula uma "fotografia" com código de verificação; depois disso o mês não muda. **Verificar** recalcula e compara; **reabrir** exige um motivo (só o último fechamento). → `/schools/{s}/closings...`.
- **Relatórios** (PDF/planilha, `/schools/{s}/reports/...`): fechamento do mês, **Livro Caixa** (planilha e PDF), contribuições do mês, relatório de **uma página para a comunidade** (sem nomes), **pacote do mês** (ZIP com o livro e os anexos das despesas).
- **Balancete** (formato da folha da contadora): `GET /schools/{s}/balancete` e `.pdf`. Mostra saldo anterior por lugar (caixa, banco, aplicação), receitas, bens permanentes, despesas por categoria e o saldo final. O que o livro não sabe (**saldo de quando a escola começou**; **caixa e aplicação** do fim de cada mês) a secretaria digita: `POST /schools/{s}/balancete/balances`. O banco é o que sobra do total.

### F. Conciliação com o banco
1. Cadastrar a conta (só os **últimos dígitos**; a finalidade é "geral" ou "PDDE"). → `/reconciliation/accounts`.
2. **Importar o extrato** em OFX, CSV ou PDF de texto (PDF escaneado não é lido). → `/reconciliation/imports` (e `/imports/preview` para ver antes). CPF e CNPJ são **mascarados** antes de guardar. Linhas lidas de PDF exigem que a secretaria confirme que conferiu.
3. **Comparar** o extrato com o livro: o que bate, o que só está no banco, o que só está no livro, o que diverge. → `GET /reconciliation/imports/{id}`.
3b. **Cada conta compara com o dinheiro da sua carteira**: a conta **geral** com as despesas da APM, a conta do **PDDE** com as despesas decididas como PDDE. Uma saída que é dinheiro da outra carteira aparece como aviso ("saiu da conta errada"). As linhas da conta do PDDE não se registram no caixa da APM: são tratadas na tela do PDDE, onde a linha mostra a despesa que ela paga e sugere o item e custeio ou capital.
4. Para cada linha só do banco: **registrar** (Pix direto, transferência, tarifa) ou **ignorar com motivo**. Cada linha é resolvida **uma só vez**. → `/reconciliation/lines/{id}/actions`.
5. O saldo do extrato pode alimentar o fechamento. → `/reconciliation/closing-balance`.

### G. PDDE (dinheiro federal)
A lei pede que a escola prove **cada linha do extrato da conta do PDDE**. O sistema é o caderno de trabalho:
1. A conta do PDDE é cadastrada e o extrato importado (fluxo F). Só linhas de conta com finalidade PDDE entram aqui.
2. **Classificar** cada linha: **repasse**, **rendimento**, **despesa** (programa, custeio ou capital, objeto), **devolução ao FNDE**, imposto pago à prefeitura, estorno ou despesa não elegível. Mudar a classificação cria uma decisão nova (vale a última; a antiga fica guardada). → `POST /schools/{s}/pdde/lines/{id}/classification`.
3. **Documentos da despesa** (NF-e com chave de 44 números conferida pelo dígito final, fatura, recibo): vários por linha, nunca somando mais que a linha. Errou? **Anular** (nunca apaga). → `.../lines/{id}/documents`, `.../documents/{id}/void`.
4. A situação de cada linha é **pendente**, **parcial** ou **concluída**. **Avisos**: tarifa bancária na conta do PDDE (proibida), gasto maior que o recebido em custeio/capital, falta do extrato de dezembro, prazo. → `GET .../pdde/lines`, `.../summary`.
5. Dados que os formulários pedem: **entidade** (nome no CNPJ, CNPJ, endereço) e **saldo que veio do ano anterior**. → `/pdde/entity`, `/pdde/carryovers`.
6. **Formulários oficiais do FNDE em PDF** (sem barras coloridas; avisos "Conferir antes de assinar" no topo):
   - **Demonstrativo** (um por programa e ano): `.../pdde/forms/demonstrativo.pdf`
   - **Relação de bens** (só capital): `.../pdde/forms/bens.pdf`
   - **Conciliação bancária** (uma conta): `.../pdde/forms/conciliacao.pdf`
   - Mais um relatório do ano em PDF e planilha, na ordem do extrato: `.../pdde/report.pdf` e `.csv`.

**Quem presta contas no sistema do governo é a Secretaria de Educação, não a escola.** A escola monta a documentação nos formulários oficiais do FNDE (é isso que o sistema gera), assina e entrega o papel, com os documentos, à Secretaria, que lança no sistema. Esse fluxo é da lei e não muda.

### H. Impostos retidos
1. A secretaria escreve as **regras** (alíquota, teto, código da guia ou como pagar, vencimento) **lendo a lei e os sites do governo**. O sistema **não traz nenhuma regra como verdade**. Marcar "conferi" **exige o endereço da fonte oficial**. → `/schools/{s}/tax/rules`.
2. Cada serviço pago com retenção é **registrado** (empresa ou pessoa física, nome, mês, valor bruto). O sistema calcula o retido e mostra antes de salvar. A retenção guarda a versão exata da regra usada. Errou? **Anular**. → `/tax/preview`, `/tax/retentions`.
3. No mês seguinte, a **"cola"**: por imposto, **valor a pagar, código, período e vencimento** (sem considerar feriados) e um botão para o site da Receita. → `GET /tax/month`.
4. Pagou? Registre a saída em Despesas, na categoria "Impostos retidos e tributos pagos".

### I. Pessoas e acesso
- **Convidar** (`POST /employees` ou `/invitations`): a pessoa recebe e-mail com link, escolhe a senha (`POST /invitations/accept`). **Suspender/reativar** derruba o acesso na próxima requisição.
- **Entrar**: e-mail e senha (`/auth/login`), trocar de contexto (`/auth/context`), sair, trocar senha (derruba todas as sessões), esqueci a senha (`/auth/password-reset/...`: a resposta é igual para qualquer e-mail).
- **Forklin (opcional, desligado se não configurado)**: "Entrar com Forklin" (`/forklin/sso/start` → painel Forklin → `/forklin/sso/callback`). A Central avisa mudanças de acesso em `POST /forklin/events` (ex.: revogar o acesso de alguém encerra as sessões na hora).

### J. Configurações da escola
Nome e endereço do link (mudar o endereço tem limite: duas trocas livres, depois 15 dias; **endereços antigos continuam abrindo a escola**, para o QR impresso não quebrar), valores sugeridos, texto do valor livre, **meta e número esperado de contribuições** (alimentam "meta e adesão"), link público e **cartaz A4 com QR code**. → `/schools/{s}/identity`, `/settings`, `/public-link`, `/public-link/poster.pdf`.

---

## 5. Todas as rotas da API (resumo)
`P` = pública (sem login). Permissões: **sec** = secretaria; **func** = funcionário; **ler** = quem lê relatórios.

**Saúde e entrada**
| Rota | Quem | O que faz |
|---|---|---|
| `GET /api/health`, `/api/health/ready` | P | O sistema está vivo / pronto (banco ok). |
| `POST /auth/login`, `/auth/logout` | P | Entrar e sair. |
| `GET /auth/me` | logado | Quem sou eu e onde atuo. |
| `POST /auth/context` | logado | Trocar a escola ativa. |
| `POST /auth/password` | logado | Trocar a senha (encerra todas as sessões). |
| `POST /auth/password-reset/request`, `/confirm` | P | Esqueci a senha / escolher a nova. |
| `POST /invitations`, `/invitations/accept` | sec / P | Convidar / aceitar convite. |
| `GET/POST /forklin/sso/start`, `/callback`, `POST /forklin/events` | P | Entrar com Forklin e avisos da Central. |

**Página pública da família** (todas P)
| Rota | O que faz |
|---|---|
| `GET /public/schools/{slug}` | Dados da página (valores, limites, campos). |
| `POST /public/schools/{slug}/contributions` | Começar uma contribuição (cria a cobrança Pix). |
| `GET .../contributions/{token}/charge` | Estado do pagamento (a página consulta). |
| `POST .../contributions/{token}/charges` | Nova cobrança se a anterior venceu. |
| `GET .../contributions/{token}/receipt` | Comprovante (só depois de pago). |
| `GET .../campaigns`, `.../campaigns/{id}`, `/cover`, `/items/{id}/image` | Ver campanhas, capa e fotos. |
| `POST .../campaigns/{id}/orders` | Fazer um pedido (cria a contribuição e o Pix). |
| `POST /webhooks/pix/sandbox`, `/webhooks/pix/bb` | Aviso do provedor de Pix (o sistema confirma antes de crer). |
| `POST /dev/sandbox/pix/{txid}/pay` | **Só em desenvolvimento**: simula o pagamento. |

**Despesas e pedidos**
| Rota | Quem | O que faz |
|---|---|---|
| `GET /expense-categories` | func | Categorias de saída. |
| `GET/POST /expenses`, `GET/PATCH /expenses/{id}` | func (ver as próprias) / sec (ver todas) | Listar, criar, ver e editar (autor, em rascunho/correção). |
| `POST .../attachments`, `GET .../attachments/{id}` | func / quem vê | Anexar e baixar nota ou comprovante. |
| `POST .../submit` | func | Enviar para aprovação (exige anexo). |
| `POST .../approve`, `/reject`, `/request-correction` | sec | Decidir (nunca a própria). |
| `POST .../pay`, `.../reimburse` | sec | Registrar pagamento da APM / reembolso do funcionário. |
| `POST .../cancel` | autor / sec | Cancelar. |
| `GET/POST .../expenses/ocr` | func | Ler foto da nota (só sugere; desligado por padrão). |
| `GET/POST /requests`, `GET .../{id}`, `.../attachments` | func / sec | Pedidos à secretaria e fotos. |
| `POST .../requests/{id}/start`, `/resolve`, `/cancel` | sec / autor | Assumir, resolver, retirar. |

**Mês, fechamento e relatórios**
| Rota | Quem | O que faz |
|---|---|---|
| `POST /contributions` | sec | Registrar contribuição em dinheiro/transferência. |
| `GET /statement`, `/statement/summary`, `/pending`, `/series`, `/goal` | sec (alguns também ler) | Extrato, dashboard, pendências, gráfico, meta e adesão. |
| `GET/POST /closings`, `GET /closings/{id}` | sec / ler | Listar, fechar e ver fechamentos. |
| `POST /closings/{id}/verify`, `/reopen` | sec | Verificar / reabrir (com motivo). |
| `GET /closings/{id}/report.pdf` | ler | PDF do fechamento. |
| `GET /reports/cash-book.csv`, `/cash-book.pdf` | ler | Livro Caixa. |
| `GET /reports/contributions.pdf`, `/community.pdf` | ler | Contribuições; uma página para a comunidade (sem nomes). |
| `GET /reports/month-package.zip` | sec | Pacote do mês. |
| `GET /balancete`, `/balancete.pdf`, `POST /balancete/balances` | ler / sec | Balancete e saldos digitados. |

**Banco, PDDE e impostos** (todas sec)
| Rota | O que faz |
|---|---|
| `GET/POST /reconciliation/accounts`, `PATCH .../{id}` | Contas do banco. |
| `GET/POST /reconciliation/imports`, `POST .../imports/preview`, `GET .../imports/{id}` | Importar, pré-visualizar e comparar o extrato. |
| `POST /reconciliation/lines/{id}/actions` | Registrar ou ignorar uma linha. |
| `GET /reconciliation/closing-balance` | Saldo dos extratos até o fim do mês. |
| `GET /pdde/lines`, `/pdde/summary` | Linhas do mês; saldo por programa e avisos. |
| `POST /pdde/lines/{id}/classification`, `.../documents`, `/pdde/documents/{id}/void` | Classificar, comprovar e anular documento. |
| `GET/POST /pdde/entity`, `/pdde/carryovers` | Dados da entidade; saldo do ano anterior. |
| `GET /pdde/forms/demonstrativo.pdf`, `/bens.pdf`, `/conciliacao.pdf` | Os três formulários do FNDE. |
| `GET /pdde/report.pdf`, `/report.csv` | Relatório do ano. |
| `GET/POST /tax/rules`, `GET /tax/preview`, `GET /tax/month`, `POST /tax/retentions`, `.../{id}/void` | Impostos (fluxo H). |

**Campanhas, pessoas e configurações** (sec)
| Rota | O que faz |
|---|---|
| `GET/POST /campaigns`, `GET/PATCH /campaigns/{id}` | Listar, criar, ver e editar campanhas. |
| `POST .../activate`, `.../end` | Pôr à venda / encerrar. |
| `POST .../items`, `PATCH .../items/{id}`, `GET/PUT/DELETE` das imagens | Produtos e fotos (capa e item). |
| `GET .../dashboard`, `GET .../orders`, `POST .../orders/delivery`, `GET .../report.pdf` | Arrecadação, pedidos, entrega e PDF. |
| `GET/POST /employees`, `.../activate`, `.../suspend`, `.../invitations/{id}/resend`, `DELETE .../invitations/{id}` | Pessoas e convites. |
| `GET/PATCH /identity`, `GET/PATCH /settings`, `GET /public-link`, `GET /public-link/poster.pdf` | Configurações da escola. |

---

## 6. Regras que o sistema impõe (e por quê)
- **Cada escola só vê a sua**: o banco recusa cruzamentos, mesmo se o código errasse.
- **O livro financeiro nunca apaga nem edita**: erros se corrigem com uma linha nova; tudo fica na auditoria (quem, o quê, quando; **sem copiar textos livres ou documentos pessoais**).
- **Mês fechado não muda** e fecha em ordem. Reabrir exige motivo.
- **Quem aprova não escreve**: ninguém aprova a própria despesa.
- **O Pix só vale depois de o provedor confirmar**; valor diferente vai para revisão.
- **Dados pessoais**: extratos têm CPF/CNPJ mascarados; relatórios para a comunidade saem sem nomes.
- **Nada é "verdade" por padrão em impostos**: a escola escreve a regra e anota a fonte oficial.
- **Formulários listam o que falta** em vez de esconder.

## 7. O que o sistema NÃO faz
- Não envia nada ao governo, à Secretaria de Educação nem à Receita; não emite guia (DARF) nem paga imposto.
- Não movimenta dinheiro; não cobra Pix real enquanto o gateway não for ligado.
- Não lê PDF escaneado (imagem); não calcula feriado no vencimento do imposto.
- Não tem Rol de Materiais, Consolidação de Pesquisa de Preços nem Termo de Doação do FNDE.
- O saldo que a escola já tinha **antes** de usar o sistema entra no balancete e nos formulários do PDDE, mas **ainda não** no fechamento (a "diferença do banco" do fechamento mostra esse valor).

## 8. Para quem opera (produção)
- **Sobe**: site (Next.js) + API (FastAPI) + banco PostgreSQL 16 próprio, tudo no Dokploy, um só domínio. Ver `docs/deploy-dokploy.md`.
- **Migrações novas desta versão (0027 a 0030)**: balancete, PDDE, impostos e formulários. São **aditivas** e rodam sozinhas no início da API. **Faça backup do banco antes.**
- **Desligado de propósito**: Pix real (`PIX_LIVE_ENABLED=false`), leitura de nota por foto, integração Forklin (se não configurada).
- **Ambiente de teste com dados de mentira**: `docs/sandbox.md` (escola fictícia com setembro e outubro).
- **Mais detalhe**: `docs/financial-model.md` (livro), `docs/statement.md` (extrato, fechamento, balancete), `docs/m8-pdde-plan.md` (PDDE), `docs/tax-guides.md` (impostos), `docs/auth.md` (acesso).
