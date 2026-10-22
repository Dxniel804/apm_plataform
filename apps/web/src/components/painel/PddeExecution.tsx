"use client";

import { useState } from "react";
import { ChevronDownThinIcon, PieIcon } from "@/components/ui/icons";
import type { PddeAlert, PddeProgramBalance } from "@/lib/api/pdde";
import { formatBRL } from "@/lib/money";
import { programName } from "@/lib/pdde-objects";
import { BLUES, SegmentBar } from "./SegmentBar";

const keyOf = (p: PddeProgramBalance) => `${p.program}-${p.programLabel ?? ""}`;

/**
 * "Execucao por programa": de tudo que um programa tinha, quanto ja foi gasto em custeio, quanto em capital e quanto
 * ainda e saldo. "Todos" soma os programas (e tudo dinheiro do PDDE); o seletor mostra um de cada vez. Os valores sao os
 * do servidor: o saldo e dele (calculado por categoria, nao e "entrou menos gastou") e o aviso de "gastou mais do que
 * entrou" tambem; a barra so os poe lado a lado.
 */
export function PddeExecution({ programs, alerts }: { programs: PddeProgramBalance[]; alerts: PddeAlert[] }) {
  const [chosen, setChosen] = useState("all");
  if (programs.length === 0) return null;

  const picked = chosen === "all" ? programs : programs.filter((p) => keyOf(p) === chosen);
  const sum = (pick: (p: PddeProgramBalance) => number) => picked.reduce((total, p) => total + pick(p), 0);
  const custeio = sum((p) => p.spentCusteioCents);
  const capital = sum((p) => p.spentCapitalCents);
  const balance = sum((p) => Math.max(p.balanceCents, 0));
  const overs = alerts.filter((a) => a.code === "spent_over_received" && picked.some((p) => p.program === a.program));

  return (
    <section aria-labelledby="pdde-exec-title" className="h-full rounded-[var(--r-lg)] border border-line p-6">
      <div className="flex min-h-11 flex-wrap items-center justify-between gap-3">
        <h2 id="pdde-exec-title" className="flex items-center gap-2.5 text-[1rem] font-medium text-ink">
          <PieIcon size={20} className="text-ink-2" aria-hidden="true" />
          Execução por programa
        </h2>
        {programs.length > 1 && (
          <div className="relative">
            <label htmlFor="pdde-exec-program" className="sr-only">
              Programa
            </label>
            <select
              id="pdde-exec-program"
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
              className="min-h-10 cursor-pointer appearance-none rounded-full border border-pill-line bg-pill pl-5 pr-10 text-sub font-semibold text-brand-800 transition-colors hover:border-brand-300 hover:bg-[#d3e4ff]"
            >
              <option value="all">Todos</option>
              {programs.map((p) => (
                <option key={keyOf(p)} value={keyOf(p)}>
                  {programName(p.program, p.programLabel)}
                </option>
              ))}
            </select>
            <ChevronDownThinIcon size={14} className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-brand-800" />
          </div>
        )}
      </div>

      <div className="mt-6">
        {custeio + capital + balance > 0 ? (
          <SegmentBar
            label="Execução do PDDE"
            segments={[
              { key: "custeio", label: "Custeio gasto", weight: custeio, value: formatBRL(custeio), color: BLUES[0] },
              { key: "capital", label: "Capital gasto", weight: capital, value: formatBRL(capital), color: BLUES[1] },
              { key: "balance", label: "Saldo", weight: balance, value: formatBRL(balance), color: BLUES[2] },
            ]}
          />
        ) : (
          <p className="text-body text-ink-2">Nada gasto e sem saldo ainda.</p>
        )}
      </div>

      {overs.map((a) => (
        <p key={`${a.program}-${a.economicCategory}`} role="note" className="mt-4 rounded-[var(--r-md)] bg-info-soft px-4 py-2.5 text-sub text-brand-800">
          {programName(a.program, null)}: {formatBRL(a.cents)} de {a.economicCategory === "CAPITAL" ? "capital" : "custeio"} a mais do que entrou.
        </p>
      ))}
    </section>
  );
}
