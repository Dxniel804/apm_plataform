"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Amount } from "@/components/ui/Amount";
import { ArrowDownIcon, ArrowUpIcon, BankIcon, ListIcon } from "@/components/ui/icons";
import { ButtonLink } from "@/components/ui/Button";
import { api } from "@/lib/api";
import type { PddeMonth, PddeYear } from "@/lib/api/pdde";
import type { ApiResult } from "@/lib/api/types";
import { currentLocalPeriod, periodLabel } from "@/lib/statement-labels";
import { KpiCards } from "./KpiCards";
import { PddeExecution } from "./PddeExecution";
import { BLUES, SegmentBar } from "./SegmentBar";

interface Props {
  schoolId: string;
  /** YYYY-MM da URL; sem ele, o mes corrente. */
  period: string | undefined;
}

function lineState(line: PddeMonth["lines"][number]): { label: "Classificar" | "Falta nota" | "Pronto" } {
  const c = line.classification;
  if (!c) return { label: "Classificar" };
  if (c.kind === "EXPENSE" && line.status !== "DONE") return { label: "Falta nota" };
  return { label: "Pronto" };
}

const MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
/** "2026-10-06" -> "6 out" (um DIA, nao um instante: nao passa por fuso). */
const shortDay = (day: string) => {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(day);
  return m ? `${Number(m[2])} ${MONTHS_SHORT[Number(m[1]) - 1]}` : day;
};



/**
 * O PDDE na dashboard: os mesmos tres numeros do caixa da APM (saldo, entrou, saiu), a execucao de cada programa e so os
 * lancamentos que pedem acao; a lista inteira do extrato fica na tela do PDDE. Nada e somado ao caixa da APM. Os numeros
 * vem das mesmas rotas da tela do PDDE.
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
  // The balance is what the bank says (the latest statement up to the month); what was classified is only a split of it.
  const classified = y.programs.reduce((sum, p) => sum + p.balanceCents, 0);
  const known = m.bankBalances.filter((b) => b.balanceCents !== null);
  const bank = known.length > 0 ? known.reduce((sum, b) => sum + (b.balanceCents ?? 0), 0) : null;
  const asOf = known.map((b) => b.asOf).filter((d): d is string => d !== null).sort().at(-1) ?? null;
  const gap = bank === null ? 0 : bank - classified;
  const count = (label: "Pronto" | "Falta nota" | "Classificar") => m.lines.filter((l) => lineState(l).label === label).length;
  const plural = (n: number) => `${n} ${n === 1 ? "lançamento" : "lançamentos"}`;
  const [ready, noReceipt, toClassify] = [count("Pronto"), count("Falta nota"), count("Classificar")];
  // The year's count also has what is in other months; only said when it is more than what this month lists.
  const elsewhere = Math.max(y.pendingCount - noReceipt - toClassify, 0);

  return (
    <div className="space-y-6">
      <KpiCards
        label="Números do PDDE"
        items={[
          {
            key: "balance",
            icon: <BankIcon size={20} />,
            label: bank !== null ? "Saldo na conta" : "Saldo classificado",
            value: <Amount cents={bank ?? classified} centsClassName="text-[0.5em] font-medium" />,
            note: (
              <>
                {bank !== null && asOf && <p>Extrato de {shortDay(asOf)}</p>}
                {bank === null && <p>Sem extrato importado</p>}
                {bank !== null && gap > 0 && (
                  <p className="font-medium text-brand-800">
                    <Amount cents={gap} /> ainda sem classificar
                  </p>
                )}
                {bank !== null && gap < 0 && (
                  <p className="font-medium text-brand-800">
                    Classificação <Amount cents={-gap} /> acima do banco
                  </p>
                )}
              </>
            ),
          },
          { key: "in", icon: <ArrowDownIcon size={20} />, label: "Entrou", value: <Amount cents={inCents} centsClassName="text-[0.5em] font-medium" /> },
          { key: "out", icon: <ArrowUpIcon size={20} />, label: "Saiu", value: <Amount cents={outCents} centsClassName="text-[0.5em] font-medium" /> },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <PddeExecution programs={y.programs} alerts={y.alerts} />

        <section aria-labelledby="pdde-lines-title" className="h-full rounded-[var(--r-lg)] border border-line p-6">
          <div className="flex min-h-11 flex-wrap items-center justify-between gap-3">
            <h2 id="pdde-lines-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
              <ListIcon size={20} className="text-ink-2" aria-hidden="true" />
              Lançamentos do mês
            </h2>
            <ButtonLink href="/painel/pdde" variant="secondary" size="md" className="rounded-full">
              Abrir o PDDE
            </ButtonLink>
          </div>
          <div className="mt-6">
            {m.lines.length === 0 ? (
              <p className="text-body text-ink-2">Nenhum lançamento em {periodLabel(month)}.</p>
            ) : (
              <SegmentBar
                label="Situação dos lançamentos"
                segments={[
                  { key: "ready", label: "Prontos", weight: ready, value: plural(ready), color: BLUES[0] },
                  { key: "noreceipt", label: "Falta nota", weight: noReceipt, value: plural(noReceipt), color: BLUES[1] },
                  { key: "classify", label: "Falta classificar", weight: toClassify, value: plural(toClassify), color: BLUES[2] },
                ]}
              />
            )}
          </div>
          {elsewhere > 0 && <p className="mt-3 text-sub text-ink-2">{elsewhere === 1 ? "1 em outro mês" : `${elsewhere} em outros meses`} do ano.</p>}
        </section>
      </div>
    </div>
  );
}
