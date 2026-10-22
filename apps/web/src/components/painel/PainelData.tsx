"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, buttonClass } from "@/components/ui/Button";
import { CalendarIcon, CashCoinIcon, ChevronDownThinIcon, ClockIcon, DownloadIcon, XLgIcon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import { contributionsPdfHref } from "@/lib/api/statement";
import type { ApiError, ApiResult, GoalAdhesion, Page, PendingEntry, SeriesPoint, StatementEntry, StatementSummary } from "@/lib/api/types";
import { describeAuthError } from "@/lib/auth-messages";
import { formatBRL } from "@/lib/money";
import { sectionHref, type PainelSection } from "@/lib/painel-section";
import { KIND_LABELS, type MovementKind } from "@/lib/status";
import { PENDING_SECTIONS, periodLabel, pendingSectionTitle, recentPeriods, currentLocalPeriod } from "@/lib/statement-labels";
import { CashContributionForm } from "./CashContributionForm";
import { BalanceTrend } from "./BalanceTrend";
import { GoalCard } from "./GoalCard";
import { KIND_META } from "./kinds";
import { BLUES, SegmentBar } from "./SegmentBar";
import { PendingRows, StatementList } from "./StatementList";
import { StatementIndicators } from "./StatementIndicators";

type Res<T> = { state: "loading" } | { state: "ready"; data: T } | { state: "forbidden" } | { state: "error"; message: string };

function toRes<T>(result: ApiResult<T>): Res<T> {
  if (result.ok) return { state: "ready", data: result.data };
  if (result.error.status === 403) return { state: "forbidden" };
  return { state: "error", message: describeError(result.error) };
}

function describeError(error: ApiError): string {
  if (error.kind === "problem" && error.code === "validation_error") return "Esse mês não é válido.";
  return describeAuthError(error, "context");
}

const LOADING: Res<never> = { state: "loading" };

function Skeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="rounded-[var(--r-lg)] border border-line p-6">
        <div className="skeleton h-4 w-40" />
        <div className="skeleton mt-4 h-12 w-64 max-w-full" />
        <div className="skeleton mt-8 h-16 w-full" />
      </div>
    </div>
  );
}

function Notice({ tone, children }: { tone: "info" | "bad"; children: React.ReactNode }) {
  return (
    <p
      role={tone === "bad" ? "alert" : "note"}
      className={`rounded-[var(--r-md)] px-4 py-3 text-sub ${tone === "bad" ? "bg-bad-soft font-medium text-bad" : "bg-info-soft text-brand-800"}`}
    >
      {children}
    </p>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-[var(--r-lg)] border border-line px-6 py-12 text-center">
      <h2 className="text-heading">{title}</h2>
      <p className="mx-auto mt-2 max-w-[44ch] text-body text-ink-2">{text}</p>
    </div>
  );
}

interface PainelDataProps {
  /** `school.id` do vinculo ATIVO da sessao. Nunca vem de URL nem de campo do usuario. */
  schoolId: string;
  section: PainelSection;
  /** YYYY-MM vindo da URL; sem ele a API usa o mes corrente no fuso da escola. */
  period: string | undefined;
  permissions: string[];
  onPeriodChange: (period: string) => void;
  /** O que abre a barra de ferramentas, na mesma linha do mes e dos botoes (na dashboard: as abas APM | PDDE). */
  leading?: React.ReactNode;
}

/**
 * Numeros REAIS da escola do vinculo ativo (docs/statement.md): resumo do mes, lancamentos por tipo
 * (com "carregar mais"), pendencias fora do saldo e as acoes da gestao. Cada rota que responder 403
 * (perfil `viewer` so le o resumo) vira um aviso: a tela nao quebra.
 */
export function PainelData({ schoolId, section, period, permissions, onPeriodChange, leading }: PainelDataProps) {
  const canReadStatement = permissions.includes("statement:read");
  const canRecordCash = permissions.includes("contributions:record_cash");
  const canReadReports = permissions.includes("reports:read") || permissions.includes("reports:read_aggregate");
  const kind: MovementKind | null = section === "resumo" ? null : section;

  const [reload, setReload] = useState(0);
  const [cashOpen, setCashOpen] = useState(false);
  const [latest] = useState(() => currentLocalPeriod());

  // Cada recurso guarda a chave do pedido que o gerou: chave diferente = ainda carregando (sem setState sincrono no efeito).
  const summaryKey = `${schoolId}|${period ?? ""}|${reload}`;
  const [summaryState, setSummaryState] = useState<{ key: string; res: Res<StatementSummary> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.statement.summary(schoolId, period).then((result) => {
      if (!cancelled) setSummaryState({ key: summaryKey, res: toRes(result) });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, summaryKey]);
  const summary: Res<StatementSummary> = summaryState?.key === summaryKey ? summaryState.res : LOADING;

  // O grafico de evolucao e o cartao de meta e adesao: so no resumo. Se falharem, o resto da tela segue.
  const extrasKey = `${schoolId}|${period ?? ""}|${reload}`;
  const [extrasState, setExtrasState] = useState<{ key: string; series: SeriesPoint[] | null; goal: GoalAdhesion | null } | null>(null);
  useEffect(() => {
    if (section !== "resumo") return;
    let cancelled = false;
    void Promise.all([api.statement.series(schoolId, { period, months: 6 }), api.statement.goal(schoolId, period)]).then(([series, goal]) => {
      if (!cancelled) setExtrasState({ key: extrasKey, series: series.ok ? series.data : null, goal: goal.ok ? goal.data : null });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, section, extrasKey]);
  const extras = extrasState?.key === extrasKey ? extrasState : null;
  const canConfigure = permissions.includes("school_settings:manage");

  const entriesKey = `${schoolId}|${period ?? ""}|${kind ?? ""}|${reload}`;
  const [entriesState, setEntriesState] = useState<{ key: string; res: Res<Page<StatementEntry>> } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  useEffect(() => {
    if (!kind || !canReadStatement) return;
    let cancelled = false;
    void api.statement.entries(schoolId, { period, kind, limit: 50 }).then((result) => {
      if (!cancelled) setEntriesState({ key: entriesKey, res: toRes(result) });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, kind, canReadStatement, entriesKey]);
  const entries: Res<Page<StatementEntry>> = entriesState?.key === entriesKey ? entriesState.res : LOADING;

  async function loadMore() {
    if (entries.state !== "ready" || !entries.data.nextCursor || loadingMore) return;
    setLoadingMore(true);
    setMoreError(null);
    const result = await api.statement.entries(schoolId, { period, kind: kind ?? undefined, limit: 50, cursor: entries.data.nextCursor });
    setLoadingMore(false);
    if (!result.ok) {
      setMoreError(describeError(result.error));
      return;
    }
    setEntriesState({
      key: entriesKey,
      res: { state: "ready", data: { items: [...entries.data.items, ...result.data.items], nextCursor: result.data.nextCursor } },
    });
  }

  const pendingKey = `${schoolId}|${reload}`;
  const [pendingState, setPendingState] = useState<{ key: string; res: Res<Page<PendingEntry>> } | null>(null);
  useEffect(() => {
    if (section !== "resumo" || !canReadStatement) return;
    let cancelled = false;
    void api.statement.pending(schoolId, { limit: 100 }).then((result) => {
      if (!cancelled) setPendingState({ key: pendingKey, res: toRes(result) });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, section, canReadStatement, pendingKey]);
  const pending: Res<Page<PendingEntry>> = pendingState?.key === pendingKey ? pendingState.res : LOADING;

  const effectivePeriod = summary.state === "ready" ? summary.data.period : (period ?? null);
  const periods = effectivePeriod ? Array.from(new Set([...recentPeriods(latest, 12), effectivePeriod])).sort().reverse() : [];

  const toolbar = (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
      {leading}
      {effectivePeriod && (
        <div className="relative">
          <label htmlFor="period-select" className="sr-only">
            Mês
          </label>
          <CalendarIcon size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-brand-800" />
          <select
            id="period-select"
            value={effectivePeriod}
            onChange={(e) => onPeriodChange(e.target.value)}
            className="min-h-10 w-full cursor-pointer appearance-none rounded-full border border-pill-line bg-pill pl-10 pr-10 text-sub font-semibold text-brand-800 transition-colors hover:border-brand-300 hover:bg-[#d3e4ff] sm:w-auto"
          >
            {periods.map((p) => (
              <option key={p} value={p} className="bg-white text-ink">
                {periodLabel(p)}
              </option>
            ))}
          </select>
          <ChevronDownThinIcon size={14} className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-brand-800" />
        </div>
      )}
      {canRecordCash && (
        <Button variant="secondary" size="md" aria-haspopup="dialog" onClick={() => setCashOpen(true)} className="min-h-10 rounded-full px-4">
          <CashCoinIcon size={16} />
          Contribuição em dinheiro
        </Button>
      )}
      {canReadReports && summary.state === "ready" && (
        <>
          {/* Navegacao comum (o navegador baixa o PDF com o cookie de sessao); sem fetch nem blob. */}
          <a
            href={contributionsPdfHref(schoolId, summary.data.period)}
            download
            className={buttonClass("chip", "md", "min-h-10 px-5 sm:ml-auto")}
          >
            <DownloadIcon size={16} />
            Baixar PDF <span className="sr-only">das contribuições do mês</span>
          </a>
        </>
      )}
    </div>
  );

  return (
    <div>
      {toolbar}

      <Modal open={canRecordCash && cashOpen} onClose={() => setCashOpen(false)} label="Registrar contribuição em dinheiro">
        <CashContributionForm
          schoolId={schoolId}
          onRecorded={() => setReload((n) => n + 1)}
          onClose={() => setCashOpen(false)}
        />
      </Modal>

      {section === "resumo" && (
        <div className="space-y-8">
          {summary.state === "loading" && <Skeleton label="Carregando o resumo do mês…" />}
          {summary.state === "ready" && (
            <>
              <StatementIndicators summary={summary.data} />
              {extras?.series && <BalanceTrend points={extras.series} />}
              {/* O que pede ação (pendências) e a meta do mês: duas colunas da mesma largura e da mesma altura. */}
              {(canReadStatement || extras?.goal) && (
                <div className={`grid gap-4 ${canReadStatement && extras?.goal ? "lg:grid-cols-2" : ""}`}>
                  {canReadStatement && <PendingBlock pending={pending} />}
                  {extras?.goal && <GoalCard goal={extras.goal} canConfigure={canConfigure} />}
                </div>
              )}
            </>
          )}
          {summary.state === "forbidden" && <Notice tone="info">O seu perfil não tem acesso aos números desta escola.</Notice>}
          {summary.state === "error" && <Notice tone="bad">{summary.message}</Notice>}

          {!canReadStatement && summary.state === "ready" && (
            <Notice tone="info">
              O seu perfil vê só os totais do mês. Os lançamentos e as pendências são da gestão.
            </Notice>
          )}

          {canReadStatement && summary.state !== "ready" && <PendingBlock pending={pending} />}
        </div>
      )}

      {kind && (
        <section aria-labelledby="kind-title">
          <h2 id="kind-title" className="sr-only">
            {KIND_META[kind].plural}
            {effectivePeriod ? ` de ${periodLabel(effectivePeriod)}` : ""}
          </h2>
          <Link href={sectionHref("resumo", period)} className="mb-3 inline-flex min-h-11 items-center text-sub font-semibold text-brand-800 underline underline-offset-2">
            Voltar ao dashboard
          </Link>
          <p className="mb-4 max-w-[60ch] text-body text-ink-2">{KIND_META[kind].definition}</p>
          {!canReadStatement && <Notice tone="info">O seu perfil não vê os lançamentos desta escola.</Notice>}
          {canReadStatement && entries.state === "loading" && <Skeleton label="Carregando os lançamentos…" />}
          {entries.state === "forbidden" && <Notice tone="info">O seu perfil não vê os lançamentos desta escola.</Notice>}
          {entries.state === "error" && <Notice tone="bad">{entries.message}</Notice>}
          {entries.state === "ready" &&
            (entries.data.items.length === 0 ? (
              <EmptyState
                title={`Nenhuma ${KIND_LABELS[kind].toLowerCase()} neste mês`}
                text={`Quando houver ${KIND_META[kind].plural.toLowerCase()} em ${effectivePeriod ? periodLabel(effectivePeriod) : "este mês"}, elas aparecem aqui, uma por linha, com o status de cada uma.`}
              />
            ) : (
              <>
                <StatementList entries={entries.data.items} label={KIND_META[kind].plural} />
                {moreError && (
                  <p role="alert" className="mt-3 text-sub font-medium text-bad">
                    {moreError}
                  </p>
                )}
                {entries.data.nextCursor && (
                  <div className="mt-4 text-center">
                    <Button variant="secondary" onClick={loadMore} disabled={loadingMore} aria-busy={loadingMore}>
                      {loadingMore ? "Carregando…" : "Carregar mais"}
                    </Button>
                  </div>
                )}
              </>
            ))}
        </section>
      )}
    </div>
  );
}

function PendingBlock({ pending }: { pending: Res<Page<PendingEntry>> }) {
  const [openSection, setOpenSection] = useState<string | null>(null);
  if (pending.state === "loading") return <Skeleton label="Carregando as pendências…" />;
  if (pending.state === "forbidden") return <Notice tone="info">O seu perfil não vê as pendências desta escola.</Notice>;
  if (pending.state === "error") return <Notice tone="bad">{pending.message}</Notice>;

  const items = pending.data.items;
  const known = new Set(PENDING_SECTIONS.map((s) => s.section));
  // Uma linha por secao que tem item (uma "Nenhum item" nao pede nada de ninguem). A barra comporta 4 trechos: as 3
  // secoes de mais valor e, se houver mais, "Demais pendencias" com o resto; o detalhe de cada uma abre ao clicar.
  const all = [
    ...PENDING_SECTIONS.map((s) => ({ ...s, rows: items.filter((e) => e.section === s.section) })),
    { section: "OTHER", title: pendingSectionTitle("OTHER"), note: "", rows: items.filter((e) => !known.has(e.section)) },
  ]
    .filter((c) => c.rows.length > 0)
    .map((c) => ({ ...c, total: c.rows.reduce((sum, row) => sum + row.amountCents, 0) }))
    .sort((a, b) => b.total - a.total);
  const cards =
    all.length > BLUES.length
      ? [...all.slice(0, BLUES.length - 1), { section: "REST", title: "Demais pendências", note: "", rows: all.slice(BLUES.length - 1).flatMap((c) => c.rows), total: all.slice(BLUES.length - 1).reduce((sum, c) => sum + c.total, 0) }]
      : all;
  const opened = cards.find((c) => c.section === openSection) ?? null;

  return (
    <section aria-labelledby="pending-title" className="h-full rounded-[var(--r-lg)] border border-line p-6">
      <h2 id="pending-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
        <ClockIcon size={20} className="text-ink-2" aria-hidden="true" />
        Pendências
      </h2>

      {cards.length > 0 && (
        <div className="mt-6">
          <SegmentBar
            label="Pendências por situação"
            segments={cards.map((card, i) => ({
              key: card.section,
              label: card.title,
              weight: card.total,
              value: formatBRL(card.total),
              meta: card.rows.length === 1 ? "(1 item)" : `(${card.rows.length} itens)`,
              color: BLUES[i]!,
              onClick: () => setOpenSection(card.section),
              popup: "dialog" as const,
            }))}
          />
        </div>
      )}

      {items.length === 0 && (
        <p className="mt-4 text-body text-ink-2">
          <strong className="font-semibold text-ink">Nenhuma pendência</strong>
        </p>
      )}
      {pending.data.nextCursor && (
        <p className="mt-4 text-sub text-ink-2">Há mais pendências do que as mostradas: os totais cobrem só as exibidas.</p>
      )}

      <Modal open={opened !== null} onClose={() => setOpenSection(null)} label={opened?.title ?? "Pendências"}>
        {opened && (
          <div className="px-5 pb-8 pt-6 sm:px-10 sm:pb-10 sm:pt-9">
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-[clamp(1.5rem,1.1rem+1.2vw,2rem)] font-semibold leading-tight">{opened.title}</h2>
              <button
                type="button"
                onClick={() => setOpenSection(null)}
                aria-label="Fechar a janela"
                className="-mr-2 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink-3 hover:bg-info-soft"
              >
                <XLgIcon size={22} />
              </button>
            </div>
            {opened.note && <p className="mt-1 max-w-[60ch] text-body text-ink-2">{opened.note}</p>}
            <div className="mt-6">
              <PendingRows entries={opened.rows} label={opened.title} />
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
}
