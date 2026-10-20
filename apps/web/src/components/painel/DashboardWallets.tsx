"use client";

import { useEffect, useState } from "react";
import { Amount } from "@/components/ui/Amount";
import { api } from "@/lib/api";
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
 * A dashboard com um seletor APM | PDDE: o titulo diz de qual dinheiro e a tela e, ao lado, o saldo da OUTRA
 * carteira (nada e somado). A APM e a dashboard de sempre; o PDDE tem os mesmos blocos, do dinheiro federal.
 */
export function DashboardWallets({ schoolId, permissions, period, wallet, onPeriodChange, onWalletChange }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const month = period ?? latest;
  const year = Number(month.slice(0, 4));
  const [balances, setBalances] = useState<{ key: string; apm: number | null; pdde: number | null } | null>(null);
  const key = `${schoolId}|${month}`;

  useEffect(() => {
    let cancelled = false;
    void Promise.all([api.statement.summary(schoolId, period), api.pdde.year(schoolId, year)]).then(([apm, pdde]) => {
      if (cancelled) return;
      setBalances({
        key,
        apm: apm.ok ? apm.data.closingBalanceCents : null,
        pdde: pdde.ok ? pdde.data.programs.reduce((sum, p) => sum + p.balanceCents, 0) : null,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, year, key]);

  const known = balances?.key === key ? balances : null;
  const other = wallet === "apm" ? { title: "PDDE", cents: known?.pdde ?? null } : { title: "Caixa da APM", cents: known?.apm ?? null };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-3">
        <h2 className="text-heading">{WALLETS.find((w) => w.id === wallet)!.title}</h2>
        <div role="tablist" aria-label="Qual dinheiro ver" className="inline-flex rounded-full border border-line-strong bg-white p-1">
          {WALLETS.map((w) => (
            <button
              key={w.id}
              type="button"
              role="tab"
              aria-selected={wallet === w.id}
              onClick={() => wallet !== w.id && onWalletChange(w.id)}
              className={`min-h-10 rounded-full px-5 text-sub font-semibold ${wallet === w.id ? "bg-brand-800 text-white" : "text-brand-800 hover:bg-info-soft"}`}
            >
              {w.id === "apm" ? "APM" : "PDDE"}
            </button>
          ))}
        </div>
        {other.cents !== null && (
          <p className="text-sub text-ink-2">
            {other.title}: saldo <Amount cents={other.cents} />
          </p>
        )}
      </div>
      {wallet === "apm" ? (
        <PainelData schoolId={schoolId} section="resumo" period={period} permissions={permissions} onPeriodChange={onPeriodChange} />
      ) : (
        <>
          <PeriodPicker month={month} latest={latest} onChange={onPeriodChange} />
          <PddeDashboard schoolId={schoolId} period={period} />
        </>
      )}
    </div>
  );
}

function PeriodPicker({ month, latest, onChange }: { month: string; latest: string; onChange: (period: string) => void }) {
  const periods = Array.from(new Set([...recentPeriods(latest, 12), month])).sort().reverse();
  return (
    <div className="relative mb-6 inline-block">
      <label htmlFor="pdde-dashboard-period" className="sr-only">
        Mês
      </label>
      <CalendarIcon size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-brand-800" />
      <select
        id="pdde-dashboard-period"
        value={month}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-10 cursor-pointer appearance-none rounded-full border border-pill-line bg-pill pl-10 pr-10 text-sub font-semibold text-brand-800"
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
