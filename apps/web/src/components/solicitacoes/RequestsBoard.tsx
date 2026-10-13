"use client";

import { useEffect, useState } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/TextField";
import { StatusPill } from "@/components/ui/StatusPill";
import { api } from "@/lib/api";
import type { ApiResult, Page, RequestCategory, RequestStatus, StaffRequestSummary } from "@/lib/api/types";
import { formatDateShort } from "@/lib/format";
import { CATEGORY_LABELS, CATEGORY_ORDER, describeRequestError, requestStatusView } from "@/lib/request-labels";
import { RequestDetailPanel } from "./RequestDetailPanel";
import { RequestForm } from "./RequestForm";

type Scope = "mine" | "inbox";

const INBOX_FILTERS: Array<{ status: RequestStatus | undefined; label: string }> = [
  { status: "OPEN", label: "Abertas" },
  { status: "IN_PROGRESS", label: "Em andamento" },
  { status: "RESOLVED", label: "Resolvidas" },
  { status: "CANCELLED", label: "Canceladas" },
  { status: undefined, label: "Todas" },
];

interface Props {
  schoolId: string;
  /** Usuario da sessao (so para marcar "sua" e para nao oferecer ao autor o que a API recusa). */
  userId: string;
  permissions: string[];
  scope: Scope;
}

/**
 * Lista de solicitacoes da escola do vinculo ativo. "mine": as minhas, com "Nova solicitacao". "inbox": a caixa de
 * entrada da gestao, filtrada por situacao e categoria na API. Cada cartao abre o detalhe com as acoes permitidas.
 * Nada aqui decide estado: a API devolve e a tela mostra.
 */
export function RequestsBoard({ schoolId, userId, permissions, scope }: Props) {
  const [status, setStatus] = useState<RequestStatus | undefined>(scope === "inbox" ? "OPEN" : undefined);
  const [category, setCategory] = useState<RequestCategory | "">("");
  const [version, setVersion] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [extra, setExtra] = useState<{ key: string; items: StaffRequestSummary[]; next: string | null } | null>(null);
  const [moreBusy, setMoreBusy] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);

  const key = `${schoolId}|${scope}|${status ?? ""}|${category}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<Page<StaffRequestSummary>> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.requests.list(schoolId, { status, category: category || undefined, limit: 50 }).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, status, category, key]);

  const canSubmit = permissions.includes("requests:submit");
  const res = loaded?.key === key ? loaded.res : null;
  const more = extra?.key === key ? extra : null;
  const all = res && res.ok ? [...res.data.items, ...(more?.items ?? [])] : [];
  // "Minhas solicitacoes": quem le a escola toda (diretor) recebe tudo da API; aqui ficam so as dele.
  const items = scope === "mine" ? all.filter((r) => r.authorUserId === userId) : all;
  const next = more ? more.next : res && res.ok ? res.data.nextCursor : null;

  async function loadMore() {
    if (!next || moreBusy) return;
    setMoreBusy(true);
    setMoreError(null);
    const r = await api.requests.list(schoolId, { status, category: category || undefined, limit: 50, cursor: next });
    setMoreBusy(false);
    if (!r.ok) return setMoreError(describeRequestError(r.error).general);
    setExtra({ key, items: [...(more?.items ?? []), ...r.data.items], next: r.data.nextCursor });
  }

  const reload = () => setVersion((n) => n + 1);

  return (
    <div>
      {scope === "inbox" && (
        <div className="mb-6 space-y-4">
          <div role="group" aria-label="Filtrar por situação" className="flex flex-wrap gap-2.5">
            {INBOX_FILTERS.map((f) => (
              <button
                key={f.label}
                type="button"
                aria-pressed={status === f.status}
                onClick={() => {
                  setStatus(f.status);
                  setOpenId(null);
                  setBanner(null);
                }}
                className={chipClass(status === f.status)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <SelectField
            id="request-filter-category"
            label="Categoria"
            wrapperClassName="max-w-xs"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value as RequestCategory | "");
              setOpenId(null);
            }}
          >
            <option value="">Todas as categorias</option>
            {CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </SelectField>
        </div>
      )}

      {scope === "mine" && canSubmit && (
        <div className="mb-5">
          <Button variant="chip" size="md" onClick={() => setCreating(true)} className="min-h-12 px-7">
            Nova solicitação
          </Button>
        </div>
      )}
      {canSubmit && (
        <RequestForm
          schoolId={schoolId}
          open={creating}
          onClose={() => setCreating(false)}
          onSaved={(id, note) => {
            setCreating(false);
            setBanner(note);
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
          <span className="sr-only">Carregando as solicitações…</span>
          <div aria-hidden="true" className="rounded-[var(--r-lg)] border border-line p-6">
            <div className="skeleton h-4 w-48" />
            <div className="skeleton mt-4 h-10 w-full" />
          </div>
        </div>
      )}
      {res && !res.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {res.error.status === 403 ? "O seu perfil não vê as solicitações desta escola." : describeRequestError(res.error).general}
        </p>
      )}

      {res && res.ok && items.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-12 text-center">
          <h2 className="text-heading">{scope === "mine" ? "Você ainda não abriu solicitações" : "Nenhuma solicitação nesta situação"}</h2>
          <p className="mx-auto mt-2 max-w-[44ch] text-body text-ink-2">
            {scope === "mine" ? "Use “Nova solicitação” para pedir algo à gestão, com fotos se precisar." : "Quando houver solicitações nesta situação, elas aparecem aqui."}
          </p>
        </div>
      )}

      {items.length > 0 && (
        <ul aria-label={scope === "mine" ? "Minhas solicitações" : "Solicitações da escola"} className="space-y-4">
          {items.map((r) => {
            const view = requestStatusView(r.status);
            const isOpen = openId === r.id;
            return (
              <li key={r.id} className="overflow-hidden rounded-[var(--r-lg)] border border-line bg-white">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-5 sm:px-8 sm:py-6">
                  <div className="min-w-0 flex-1 basis-56">
                    <p className="text-[1.0625rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere] sm:text-[1.25rem]">{r.title}</p>
                    <p className="mt-1 text-sub text-ink-2">
                      {CATEGORY_LABELS[r.category]} · {formatDateShort(r.createdAt)}
                      {r.attachmentsCount > 0 ? ` · ${r.attachmentsCount} ${r.attachmentsCount === 1 ? "foto" : "fotos"}` : ""}
                      {r.authorUserId === userId && scope === "inbox" ? " · sua" : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                    <StatusPill tone={view.tone}>{view.label}</StatusPill>
                  </div>
                  <Button variant="chip" size="md" aria-expanded={isOpen} aria-label={`${isOpen ? "Fechar" : "Abrir"} detalhes da solicitação ${r.title}`} onClick={() => setOpenId(isOpen ? null : r.id)} className="min-h-12 w-full px-8 sm:w-auto">
                    {isOpen ? "Fechar" : "Detalhes"}
                  </Button>
                </div>
                {isOpen && (
                  <RequestDetailPanel
                    schoolId={schoolId}
                    requestId={r.id}
                    userId={userId}
                    permissions={permissions}
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
