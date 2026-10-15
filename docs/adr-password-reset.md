# ADR: recuperação de senha (2026-10-15)

**Status:** ACEITO pelo dono do produto em 15/10/2026. Estende a lista fechada de funções privilegiadas do ADR-016.

## Contexto
Quem esqueceu a senha precisa redefini-la **sem estar logado**. Sem sessão não há contexto de escola, então o banco (RLS forçada) não mostra nada: o mesmo problema que o login e o convite resolvem com funções `SECURITY DEFINER` estreitas do papel `apm_definer`. Há e-mail real (Resend, M10 parte 1).

## Decisão
**O perímetro privilegiado cresce o mínimo possível: uma tabela e duas funções.** A troca da senha e o fim das sessões usam os caminhos que já existem para o usuário logado.

1. **Tabela `password_reset_tokens`** (id, user_id, `token_hash` SHA-256 único, `expires_at`, `used_at`, `created_at`). RLS ligada e **forçada**; o `apm_app` não tem nenhum acesso a ela. Só o `apm_definer`, com políticas estreitas: ver só tokens vivos, inserir só com validade de até 2 horas, atualizar só `used_at` (e só de um token vivo).
2. **`request_password_reset(email, token_hash, minutos)` → boolean.** Procura o usuário **ativo** pelo e-mail (sem diferenciar maiúsculas), invalida os tokens vivos anteriores dele, grava o novo e devolve `true`. Sem usuário ou inativo: `false`. Nunca devolve dados do usuário.
3. **`consume_password_reset(token_hash)` → uuid.** Marca o token como usado **se estiver vivo** e o usuário ativo, e devolve o `user_id`; senão `NULL`. Não troca a senha.
4. **A troca da senha** é feita pela API, na **mesma transação**, com o contexto do usuário devolvido e a política que já existe (`users_update_self`). As sessões são encerradas com `revoke_all_sessions` (motivo novo `password_reset`). Se algo falhar, a transação desfaz e o token continua valendo.

## Regras de segurança
- Token de 256 bits, **só o hash** no banco, uso único, validade de **30 minutos**, o pedido novo invalida o anterior.
- **O pedido responde sempre igual** (202), exista ou não a conta, e o e-mail é enviado **depois** da resposta (em segundo plano), para não revelar a diferença pelo tempo.
- **Limite de tentativas** (`login_attempts`, tipo `password_reset`): por e-mail e por IP no pedido; por IP na confirmação. Conta bloqueada por tentativas de outra pessoa não é possível: o limite do e-mail só atrasa novos pedidos.
- A confirmação responde **um único erro** para token inválido, usado, vencido ou malformado.
- A senha nova passa pela mesma regra de força da troca de senha (12 a 128 caracteres).
- Depois da troca: aviso por e-mail "sua senha foi alterada" (sem a senha) e **todas as sessões encerradas**. A pessoa entra de novo.
- O e-mail com o link traz o token (por isso o remetente real é obrigatório em produção).

## Fora do escopo
Perguntas de segurança, código por SMS, redefinição feita pela gestão para outra pessoa e limpeza dos tokens vencidos (tarefa de manutenção do M9).

## Como verificar
Testes: fluxo feliz; mesmo e-mail e e-mail inexistente com a mesma resposta; token usado, vencido, trocado por outro e malformado; pedido novo invalida o antigo; sessões encerradas; limite de tentativas; o `apm_app` não lê a tabela; as listas fechadas de políticas e funções do banco.
