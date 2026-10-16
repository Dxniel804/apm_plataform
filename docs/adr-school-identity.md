# ADR: o nome e o endereço (link) da escola, escolhidos pela escola (2026-10-16)

**Status:** ACEITO pelo dono do produto em 16/10/2026. Estende o ADR-010 (portal público por endereço) e o
[adr-forklin-sso.md](adr-forklin-sso.md) (a escola nasce vazia, com o nome da organização da Central).

## Contexto
A escola nasce com o **nome da organização da Central** e um endereço (`/escola/<endereço>`) gerado desse nome.
A secretaria precisa **escolher os dois**. Mas o endereço vai impresso em cartaz e QR Code e **as famílias pagam
por ele**: um endereço trocado que quebra, ou que passa a pertencer a outra escola, faz alguém pagar à escola errada.

## Decisão
1. **O nome muda sempre** (2 a 120 caracteres). A mudança fica na auditoria (`schools.renamed`).
2. **O endereço** (3 a 40 caracteres, minúsculas, números e hífen) **muda duas vezes sem espera**; **da terceira troca em
   diante, só 15 dias depois da troca anterior**. A regra mora num **gatilho do banco**
   (`schools_guard_identity`): nenhum código da aplicação a pula, e os contadores (`slug_changes`, `slug_changed_at`)
   não são gravados pelo papel da aplicação, só pelo gatilho. Cada troca fica na auditoria (`schools.slug_changed`).
3. **Todo endereço que uma escola já teve fica reservado a ela para sempre** (`school_slug_history`, um espaço de nomes
   único para todas as escolas, incluindo o endereço atual, preenchido para as escolas existentes na migração). Outra
   escola não pode usá-lo (409 `slug_taken`), e a própria escola pode voltar a um endereço seu.
4. **O endereço antigo continua abrindo a escola**: a função pública `resolve_school_public` também acha a escola por
   um endereço do histórico, e devolve o endereço **atual**; o site redireciona (página da escola, campanha e
   comprovante) para o atual. QR Codes e cartazes impressos continuam funcionando; os novos usam o endereço novo.
5. **Palavras reservadas** (`admin`, `api`, `login`, `painel`, `forklin`...) e endereços curtos demais são recusados
   (SQLSTATE `AP001` e `AP003`; a espera, `AP002`; a API as devolve como `slug_reserved`, `slug_too_short` e
   `slug_change_locked`).
6. **Conferência ao salvar:** se a escola já tem conta de recebimento ativa, antes de gravar o sistema confirma que
   o **endereço novo e o antigo** abrem **a mesma escola** pela busca pública que as famílias usam; se não, desfaz. A
   página pública só abre para uma escola com conta de recebimento ativa: a tela avisa, quando falta, que o link ainda
   não abre.

## O que cresce no banco (migração 0024)
`schools.slug_changes` e `schools.slug_changed_at`; a tabela `school_slug_history` (RLS forçada, só INSERT e
SELECT para a aplicação, sem UPDATE nem DELETE); duas funções de gatilho (invocador, como todas as do esquema); o
`apm_app` ganha `UPDATE (slug)` em `schools`; o `apm_definer` ganha `SELECT (slug, school_id)` e `INSERT` na
história, com políticas limitadas (a leitura, a escolas com conta ativa; a escrita, a organizações da Central).
`resolve_school_public` passa a procurar também na história.

## Rotas e telas
`GET/PATCH /api/v1/schools/{school_id}/identity` (permissão `school_settings:manage`, só a secretaria da escola).
Em *Configurações*, o cartão "Nome e endereço da escola": prévia do link, quantas trocas sem espera restam, a data em
que o endereço poderá mudar de novo, os endereços antigos e uma confirmação antes de trocar o endereço.

## Fora do escopo
Um passo de "primeiro acesso" que leve a secretaria a esse cartão; apagar um endereço do histórico (de propósito
impossível); trocar o endereço de uma escola por pedido da Forklin (um comando do operador, se for preciso).

## Como verificar
`tests/school_settings/test_identity.py` (o nome, as duas trocas livres, os 15 dias com o relógio de 14 e de 16 dias,
o banco que não deixa gravar os contadores, as palavras reservadas, o endereço de outra escola e o que ela deixou, a
volta a um endereço próprio, o endereço antigo abrindo a escola na API pública, o aviso de link ainda inativo, e quem
pode); no site, `SettingsArea.test.tsx` e `app/escola/[slug]/page.test.tsx`.

## Rollback
`alembic downgrade 0023_forklin_sso`: restaura a busca pública original, remove os gatilhos, o histórico e as colunas.
Os endereços antigos deixam de abrir; por isso só se volta com a escola avisada.
