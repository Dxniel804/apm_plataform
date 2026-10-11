"use client";

import { useEffect, useState } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { StatusPill } from "@/components/ui/StatusPill";
import { api } from "@/lib/api";
import type { ApiResult, ExpenseCategory, ExpenseStatus, ExpenseSummary, Page } from "@/lib/api/types";
import { amountSummary, describeExpenseError, expenseStatusView } from "@/lib/expense-labels";
import { formatDateShort } from "@/lib/format";
import { ExpenseDetailPanel } from "./ExpenseDetailPanel";
import { ExpenseForm } from "./ExpenseForm";

type Scope = "mine" | "queue";

const QUEUE_FILTERS: Array<{ status: ExpenseStatus | undefined; label: string }> = [
  { status: "SUBMITTED", label: "Aguardando aprovação" },
  { status: "APPROVED", label: "Aprovadas (a pagar)" },
  { status: "CORRECTION_REQUESTED", label: "Correção pedida" },
  { status: "PAID", label: "Pagas" },
  { status: "REJECTED", label: "Recusadas" },
  { status: undefined, label: "Todas" },
];

interface Props {
  schoolId: string;
  /** Usuario da sessao (so para nao oferecer ao autor o que a API recusa). */
  userId: string;
  permissions: string[];
  scope: Scope;
}

/**
 * Lista de despesas da escola do vinculo ativo. "mine": as minhas, com "Nova despesa". "queue": a fila
 * da gestao, filtrada pelo estado na API. Cada linha abre o detalhe com as acoes permitidas. Nada aqui
 * decide estado: a API devolve e a tela mostra.
 */
export function ExpensesBoard({ schoolId, userId, permissions, scope }: Props) {
  const [filter, setFilter] = useState<ExpenseStatus | undefined>(scope === "queue" ? "SUBMITTED" : undefined);
  const [version, setVersion] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [extra, setExtra] = useState<{ key: string; items: ExpenseSummary[]; next: string | null } | null>(null);
  const [moreBusy, setMoreBusy] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);

  const key = `${schoolId}|${scope}|${filter ?? ""}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<Page<ExpenseSummary>> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.expenses.list(schoolId, { status: filter, limit: 50 }).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, filter, key]);

  const canSubmit = permissions.includes("expenses:submit");
  useEffect(() => {
    if (!canSubmit) return;
    let cancelled = false;
    void api.expenses.categories(schoolId).then((r) => {
      if (!cancelled && r.ok) setCategories(r.data);
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, canSubmit]);

  const res = loaded?.key === key ? loaded.res : null;
  const more = extra?.key === key ? extra : null;
  const all = res && res.ok ? [...res.data.items, ...(more?.items ?? [])] : [];
  // "Minhas despesas": quem le a escola toda (diretor) recebe tudo da API; aqui ficam so as dele.
  const items = scope === "mine" ? all.filter((e) => e.submittedByUserId === userId) : all;
  const next = more ? more.next : res && res.ok ? res.data.nextCursor : null;

  async function loadMore() {
    if (!next || moreBusy) return;
    setMoreBusy(true);
    setMoreError(null);
    const r = await api.expenses.list(schoolId, { status: filter, limit: 50, cursor: next });
    setMoreBusy(false);
    if (!r.ok) return setMoreError(describeExpenseError(r.error).general);
    setExtra({ key, items: [...(more?.items ?? []), ...r.data.items], next: r.data.nextCursor });
  }

  const reload = () => setVersion((n) => n + 1);

  return (
    <div>
      {scope === "queue" && (
        <div role="group" aria-label="Filtrar por situação" className="mb-6 flex flex-wrap gap-2.5">
          {QUEUE_FILTERS.map((f) => (
            <button
              key={f.label}
              type="button"
              aria-pressed={filter === f.status}
              onClick={() => {
                setFilter(f.status);
                setOpenId(null);
                setBanner(null);
              }}
              className={chipClass(filter === f.status)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      {scope === "mine" && canSubmit && (
        <div className="mb-5">
          <Button variant="chip" size="md" aria-expanded={creating} onClick={() => setCreating((v) => !v)} className="min-h-12 px-7">
            {creating ? "Fechar o formulário" : "Nova despesa"}
          </Button>
        </div>
      )}

      {creating && scope === "mine" && (
        <ExpenseForm
          schoolId={schoolId}
          categories={categories}
          onCancel={() => setCreating(false)}
          onSaved={(id, note) => {
            setCreating(false);
            setBanner(note ?? null);
            setOpenId(id);
            reload();
          }}
        />
      )}

      {banner && (
        <p role="status" className="mb-4 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">
          {banner}
        </p>
      )}

      {!res && (
        <div role="status" aria-busy="true" aria-live="polite">
          <span className="sr-only">Carregando as despesas…</span>
          <div aria-hidden="true" className="rounded-[var(--r-lg)] border border-line p-6">
            <div className="skeleton h-4 w-48" />
            <div className="skeleton mt-4 h-10 w-full" />
          </div>
        </div>
      )}
      {res && !res.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {res.error.status === 403 ? "O seu perfil não vê as despesas desta escola." : describeExpenseError(res.error).general}
        </p>
      )}

      {res && res.ok && items.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-12 text-center">
          <h2 className="text-heading">{scope === "mine" ? "Você ainda não enviou despesas" : "Nenhuma despesa nesta situação"}</h2>
          <p className="mx-auto mt-2 max-w-[44ch] text-body text-ink-2">
            {scope === "mine" ? "Use “Nova despesa” para registrar uma compra e anexar a nota." : "Quando houver despesas nesta situação, elas aparecem aqui."}
          </p>
        </div>
      )}

      {items.length > 0 && (
        <ul aria-label={scope === "mine" ? "Minhas despesas" : "Despesas da escola"} className="space-y-4">
          {items.map((e) => {
            const status = expenseStatusView(e.status, e.paidBy);
            const open = openId === e.id;
            return (
              <li key={e.id} className="overflow-hidden rounded-[var(--r-lg)] border border-line bg-white">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-5 sm:px-8 sm:py-6">
                  <div className="min-w-0 flex-1 basis-56">
                    <p className="text-[1.0625rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere] sm:text-[1.25rem]">{e.description}</p>
                    <p className="mt-1 text-sub text-ink-2">
                      {e.category.name} · {formatDateShort(e.occurredAt)} · nº {e.referenceCode}
                      {e.submittedByUserId === userId && scope === "queue" ? " · sua" : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                    <p className="text-[1.25rem] font-bold tabular-nums text-brand-800 sm:text-[1.5rem]">{amountSummary(e.amountCents, e.approvedAmountCents)}</p>
                    <StatusPill tone={status.tone}>{status.label}</StatusPill>
                  </div>
                  <Button variant="chip" size="md" aria-expanded={open} aria-label={`${open ? "Fechar" : "Abrir"} detalhes da despesa nº ${e.referenceCode}`} onClick={() => setOpenId(open ? null : e.id)} className="min-h-12 w-full px-8 sm:w-auto">
                    {open ? "Fechar" : "Detalhes"}
                  </Button>
                </div>
                {open && (
                  <ExpenseDetailPanel
                    schoolId={schoolId}
                    expenseId={e.id}
                    userId={userId}
                    permissions={permissions}
                    categories={categories}
                    onChanged={(message) => {
                      if (message) setBanner(message);
                      reload();
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}

      {moreError && (
        <p role="alert" className="mt-3 text-sub font-medium text-bad">
          {moreError}
        </p>
      )}
      {next && (
        <div className="mt-4 text-center">
          <Button variant="secondary" onClick={() => void loadMore()} disabled={moreBusy} aria-busy={moreBusy}>
            {moreBusy ? "Carregando…" : "Carregar mais"}
          </Button>
        </div>
      )}
    </div>
  );
}
