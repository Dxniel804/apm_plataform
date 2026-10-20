"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Amount } from "@/components/ui/Amount";
import { StatusPill } from "@/components/ui/StatusPill";
import { api } from "@/lib/api";
import type { PddeMonth, PddeYear } from "@/lib/api/pdde";
import type { ApiResult } from "@/lib/api/types";
import { formatDayLong } from "@/lib/format";
import { currentLocalPeriod, periodLabel } from "@/lib/statement-labels";
import { programName } from "@/lib/pdde-objects";

interface Props {
  schoolId: string;
  /** YYYY-MM da URL; sem ele, o mes corrente. */
  period: string | undefined;
}

function lineState(line: PddeMonth["lines"][number]): { tone: "warning" | "info" | "success"; label: string } {
  const c = line.classification;
  if (!c) return { tone: "warning", label: "Classificar" };
  if (c.kind === "EXPENSE" && line.status !== "DONE") return { tone: line.status === "PARTIAL" ? "info" : "warning", label: "Falta nota" };
  return { tone: "success", label: "Pronto" };
}

const card = "rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-6";
const open = "inline-flex min-h-11 items-center rounded-full border border-line-strong bg-white px-5 text-sub font-semibold text-brand-800 hover:bg-bg";

/**
 * O PDDE na dashboard: os mesmos blocos do caixa da APM (entrou, saiu, saldo, lancamentos do mes), do dinheiro
 * federal. Nada e somado ao caixa da APM. Os numeros vem das mesmas rotas da tela do PDDE.
 */
export function PddeDashboard({ schoolId, period }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const month = period ?? latest;
  const year = Number(month.slice(0, 4));
  const [state, setState] = useState<{ key: string; m: ApiResult<PddeMonth>; y: ApiResult<PddeYear> } | null>(null);
  const key = `${schoolId}|${month}`;

  useEffect(() => {
    let cancelled = false;
    void Promise.all([api.pdde.month(schoolId, month), api.pdde.year(schoolId, year)]).then(([m, y]) => !cancelled && setState({ key, m, y }));
    return () => {
      cancelled = true;
    };
  }, [schoolId, month, year, key]);

  const loaded = state?.key === key ? state : null;
  if (!loaded) {
    return (
      <p role="status" aria-busy="true" className="text-sub text-ink-2">
        Carregando o PDDE…
      </p>
    );
  }
  if (!loaded.m.ok || !loaded.y.ok) {
    const forbidden = (!loaded.m.ok && loaded.m.error.status === 403) || (!loaded.y.ok && loaded.y.error.status === 403);
    return (
      <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
        {forbidden ? "O seu perfil não mexe no PDDE desta escola." : "Não foi possível carregar o PDDE. Tente de novo."}
      </p>
    );
  }

  const m = loaded.m.data;
  const y = loaded.y.data;
  if (m.accounts.length === 0) {
    return (
      <div className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center">
        <h2 className="text-heading">Falta a conta do PDDE</h2>
        <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">
          Cadastre-a em <Link className="font-semibold underline" href="/painel/conciliacao">Conciliação</Link> e importe o extrato.
        </p>
      </div>
    );
  }

  const inCents = m.lines.filter((l) => l.amountCents > 0).reduce((sum, l) => sum + l.amountCents, 0);
  const outCents = m.lines.filter((l) => l.amountCents < 0).reduce((sum, l) => sum - l.amountCents, 0);
  const balance = y.programs.reduce((sum, p) => sum + p.balanceCents, 0);
  const todo = m.lines.filter((l) => lineState(l).label !== "Pronto");

  return (
    <div className="space-y-8">
      <section aria-label="Saldo do PDDE" className={card}>
        <p className="text-foot text-ink-2">Saldo do PDDE</p>
        <p className="mt-1 text-[2.25rem] font-semibold leading-none tabular-nums text-brand-800">
          <Amount cents={balance} />
        </p>
        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-foot text-ink-2">Entrou em {periodLabel(month)}</dt>
            <dd className="text-[1.25rem] font-semibold tabular-nums text-ok">
              <Amount cents={inCents} />
            </dd>
          </div>
          <div>
            <dt className="text-foot text-ink-2">Saiu em {periodLabel(month)}</dt>
            <dd className="text-[1.25rem] font-semibold tabular-nums text-bad">
              <Amount cents={outCents} />
            </dd>
          </div>
        </dl>
      </section>

      {y.programs.length > 0 && (
        <ul aria-label="Saldo por programa" className="grid gap-3 sm:grid-cols-2">
          {y.programs.map((p) => (
            <li key={`${p.program}-${p.programLabel ?? ""}`} className={card}>
              <p className="font-semibold">{programName(p.program, p.programLabel)}</p>
              <p className="mt-1 text-sub text-ink-2">
                Entrou <Amount cents={p.receivedCents} /> · gastou <Amount cents={p.spentCusteioCents + p.spentCapitalCents} />
              </p>
              <p className="text-[1.125rem] font-bold tabular-nums text-brand-800">
                Saldo <Amount cents={p.balanceCents} />
              </p>
            </li>
          ))}
        </ul>
      )}

      <section aria-label="Pendências do PDDE" className={card}>
        {y.pendingCount > 0 ? (
          <p className="text-body">
            <strong className="font-semibold">{y.pendingCount === 1 ? "1 lançamento" : `${y.pendingCount} lançamentos`}</strong> sem classificar ou sem nota.
          </p>
        ) : (
          <p className="text-body text-ink-2">Nenhuma pendência no PDDE.</p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Link className={open} href="/painel/pdde">
            Abrir o PDDE
          </Link>
        </div>
      </section>

      <section aria-label="Lançamentos do PDDE no mês" className={card}>
        <h2 className="text-[1rem] font-medium text-ink">Lançamentos de {periodLabel(month)}</h2>
        {m.lines.length === 0 ? (
          <p className="mt-2 text-body text-ink-2">Nenhum lançamento neste mês. Importe o extrato da conta do PDDE em Conciliação.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {m.lines.slice(0, 10).map((line) => {
              const s = lineState(line);
              return (
                <li key={line.lineId} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3">
                  <span className="w-24 shrink-0 text-foot text-ink-2">{formatDayLong(line.postedOn)}</span>
                  <span className="min-w-0 flex-1 basis-48 text-sub [overflow-wrap:anywhere]">{line.memo}</span>
                  <span className={`shrink-0 text-[0.9375rem] font-semibold tabular-nums ${line.amountCents < 0 ? "text-bad" : "text-ok"}`}>
                    <Amount cents={line.amountCents} />
                  </span>
                  <StatusPill tone={s.tone}>{s.label}</StatusPill>
                </li>
              );
            })}
          </ul>
        )}
        {m.lines.length > 10 && (
          <p className="mt-3 text-foot text-ink-2">
            Mostrando 10 de {m.lines.length}. {todo.length > 0 ? `${todo.length} pedem ação.` : ""} O resto está em{" "}
            <Link className="font-semibold underline" href="/painel/pdde">
              PDDE
            </Link>
            .
          </p>
        )}
      </section>
    </div>
  );
}
