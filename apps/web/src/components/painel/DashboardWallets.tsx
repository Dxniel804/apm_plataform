"use client";

import { useState } from "react";
import { CalendarIcon, ChevronDownThinIcon } from "@/components/ui/icons";
import { currentLocalPeriod, periodLabel, recentPeriods } from "@/lib/statement-labels";
import type { Wallet } from "@/lib/painel-section";
import { PainelData } from "./PainelData";
import { PddeDashboard } from "./PddeDashboard";

interface Props {
  schoolId: string;
  permissions: string[];
  period: string | undefined;
  wallet: Wallet;
  onPeriodChange: (period: string) => void;
  onWalletChange: (wallet: Wallet) => void;
}

const WALLETS: { id: Wallet; title: string }[] = [
  { id: "apm", title: "Caixa da APM" },
  { id: "pdde", title: "PDDE" },
];

/**
 * A dashboard com um seletor APM | PDDE. As abas ficam na MESMA linha do mes e dos botoes (uma linha so, para ganhar
 * espaco); o titulo diz de qual dinheiro e a tela, mas so para leitor de tela (a aba marcada ja diz isso a quem ve).
 * A APM e a dashboard de sempre; o PDDE tem os mesmos blocos, do dinheiro federal. Nada e somado entre as duas.
 */
export function DashboardWallets({ schoolId, permissions, period, wallet, onPeriodChange, onWalletChange }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const month = period ?? latest;

  const tabs = (
    <div role="tablist" aria-label="Qual dinheiro ver" className="inline-flex self-start rounded-full border border-line-strong bg-white p-1">
      {WALLETS.map((w) => (
        <button
          key={w.id}
          type="button"
          role="tab"
          aria-selected={wallet === w.id}
          onClick={() => wallet !== w.id && onWalletChange(w.id)}
          className={`min-h-10 rounded-full px-5 text-sub font-semibold transition-colors ${wallet === w.id ? "bg-brand-800 text-white" : "text-brand-800 hover:bg-pill"}`}
        >
          {w.id === "apm" ? "APM" : "PDDE"}
        </button>
      ))}
    </div>
  );

  return (
    <div>
      <h2 className="sr-only">{WALLETS.find((w) => w.id === wallet)!.title}</h2>
      {wallet === "apm" ? (
        <PainelData schoolId={schoolId} section="resumo" period={period} permissions={permissions} onPeriodChange={onPeriodChange} leading={tabs} />
      ) : (
        <>
          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            {tabs}
            <PeriodPicker month={month} latest={latest} onChange={onPeriodChange} />
          </div>
          <PddeDashboard schoolId={schoolId} period={period} />
        </>
      )}
    </div>
  );
}

function PeriodPicker({ month, latest, onChange }: { month: string; latest: string; onChange: (period: string) => void }) {
  const periods = Array.from(new Set([...recentPeriods(latest, 12), month])).sort().reverse();
  return (
    <div className="relative">
      <label htmlFor="pdde-dashboard-period" className="sr-only">
        Mês
      </label>
      <CalendarIcon size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-brand-800" />
      <select
        id="pdde-dashboard-period"
        value={month}
        onChange={(e) => onChange(e.target.value)}
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
  );
}
