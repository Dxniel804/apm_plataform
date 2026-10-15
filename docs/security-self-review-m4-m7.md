# Autorrevisão de segurança: M4 a M7 (2026-10-15)

**Isto NÃO é a revisão independente do M9.** É uma leitura minha do que foi construído nos M4 a M7, para chegar ao revisor com os pontos já levantados. Cada item diz o que olhei, o que achei e o que foi feito.

## O que olhei
Webhook de pagamento (M4), tarifas (M4), importação de OFX, CSV e PDF (M5 a M7), ações por linha (M6), Livro Caixa e pacote do mês (M6) e a camada de arquivos.

## Pontos que estão bem
| Ponto | Como está |
|---|---|
| Perímetro privilegiado | M4 a M7 **não criaram nenhuma função `SECURITY DEFINER` nem política para o `apm_definer`**: a lista fechada de privilégios continua a mesma (os testes que a enumeram passam) |
| Webhook | A notificação é tratada como **afirmação não confiável**: autentica por segredo no cabeçalho (só o hash é comparado), grava o evento uma vez, **pergunta ao provedor o que aconteceu** antes de mudar algo, e confere o valor. Cobrança precisa pertencer à conta que autenticou |
| Tarifa do gateway | Só é gravada se `0 <= tarifa <= bruto` e uma vez por contribuição; o banco recusa o resto |
| Ações por linha | Tudo numa transação; a linha só é resolvida uma vez (chave única); PDF exige conferência marcada |
| Isolamento entre escolas | Todas as tabelas novas têm RLS forçada, auditoria e sem DELETE. Um teste confirma que outra escola recebe 404 ao agir numa linha |
| Planilha (CSV) | Textos que começam com `=`, `+`, `-`, `@` ganham um apóstrofo, para o Excel nunca executar |
| Pacote ZIP | Nomes de arquivo limpos (sem caminho), limite de 300 arquivos e 100 MB, anexo ausente listado em vez de travar |
| Leitores de arquivo | Limites de tamanho, linhas e páginas; sem XML (sem entidades), sem execução; CPF e CNPJ mascarados antes de guardar |
| Dados pessoais nos relatórios | Perfil sem direito a ver nomes recebe iniciais |

## Achados e o que fiz
| # | Achado | Gravidade | Situação |
|---|---|---|---|
| 1 | **Corpo da requisição sem teto antes de ser lido.** As rotas de webhook são públicas; o corpo JSON era lido antes da autenticação | Média | **Corrigido**: novo `BodyLimitMiddleware` recusa (413) o corpo declarado acima de 64 KB nos webhooks e 24 MB no resto, antes de a rota ler. Teste incluído. Falta o teto no proxy reverso (corpo sem tamanho declarado) |
| 2 | **O webhook usa segredo fixo no cabeçalho**, não assinatura do corpo | Média (depende do gateway) | **Em aberto, é parte do G**: gateways reais assinam o corpo (HMAC). O adaptador do gateway escolhido deve verificar a assinatura e rejeitar repetição por tempo |
| 3 | O corpo bruto do webhook é guardado (`raw_payload`, até 20 KB) sem prazo | Baixa (LGPD) | **Em aberto**: definir retenção (sugestão: apagar o corpo após o fechamento do mês, manter o resultado) |
| 4 | Limite de envios de extrato (10/min) vive na memória de **cada processo**: com vários processos, o teto real é maior | Baixa | Aceito para o MVP, igual ao OCR. Se houver mais de um processo em produção, mover para o banco |
| 5 | Leitura de PDF roda no mesmo processo da API; um PDF montado de má-fé pode gastar CPU. Só quem tem permissão de conciliação envia | Baixa a média | **Em aberto**: limites de 5 MB e 40 páginas já reduzem; ideal é rodar a leitura em processo separado com tempo máximo |
| 6 | O mesmo lançamento enviado por OFX e por CSV ou PDF pode aparecer duplicado (não há código único fora do OFX) | Funcional | Aceito; a conferência é por pessoa. Evitar misturar formatos no mesmo período |
| 7 | Chaves liga/desliga para integrações novas | Plano | **Em aberto (M9)**: pagamento real e e-mail precisam de chave que desliga rápido |
| 8 | Recuperação de senha precisa de funções privilegiadas novas | — | **Decisão sua**: ver M10 parte 2 (muda o perímetro privilegiado, pede ADR) |

## O que a revisão independente ainda deve olhar
1. As políticas e funções privilegiadas do S1 (já existentes) e a lista fechada.
2. O adaptador do gateway quando existir (assinatura, repetição, sandbox x produção).
3. Os três leitores de arquivo com arquivos maliciosos (fuzzing básico).
4. O backup e a restauração do banco antes de tocar produção.
