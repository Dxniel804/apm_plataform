import Link from "next/link";
import type { GoalAdhesion } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { periodLabel } from "@/lib/statement-labels";

function Meter({ label, value, text }: { label: string; value: number; text: string }) {
  const percent = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sub text-ink-2">{label}</p>
        <p className="text-sub font-semibold tabular-nums text-brand-800">{percent}%</p>
      </div>
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${percent}%: ${text}`} className="mt-1.5 h-3 overflow-hidden rounded-full bg-chip">
        <div className="h-full rounded-full" style={{ width: `${percent}%`, background: "var(--series-in)" }} />
      </div>
      <p className="mt-1.5 text-foot text-ink-2">{text}</p>
    </div>
  );
}

/**
 * "Meta e adesao": o arrecadado do mes contra a meta da escola e as contribuicoes pagas contra as esperadas. Fala de
 * CONTRIBUICOES, nunca de familias: a identificacao e opcional e nao da para contar familias. Sem meta, convida a
 * definir em Configuracoes (so para quem pode mexer nelas).
 */
export function GoalCard({ goal, canConfigure }: { goal: GoalAdhesion; canConfigure: boolean }) {
  const hasGoal = goal.goalCents !== null || goal.expectedContributions !== null;
  return (
    <section aria-labelledby="goal-title" className="rounded-[var(--r-lg)] border border-line p-6">
      <h2 id="goal-title" className="text-[1rem] font-medium text-ink">
        Meta e adesão em {periodLabel(goal.period)}
      </h2>
      {!hasGoal ? (
        <p className="mt-3 text-body text-ink-2">
          A escola ainda não definiu a meta do mês.{" "}
          {canConfigure && (
            <Link href="/painel/configuracoes" className="font-semibold text-brand-800 underline underline-offset-2">
              Definir em Configurações
            </Link>
          )}
        </p>
      ) : (
        <div className="mt-4 grid gap-6 sm:grid-cols-2">
          {goal.goalCents !== null && goal.goalCents > 0 && (
            <Meter label="Arrecadado" value={(goal.collectedCents / goal.goalCents) * 100} text={`${formatBRL(goal.collectedCents)} de ${formatBRL(goal.goalCents)}`} />
          )}
          {goal.expectedContributions !== null && goal.expectedContributions > 0 && (
            <Meter
              label="Contribuições pagas"
              value={(goal.paidContributions / goal.expectedContributions) * 100}
              text={`${goal.paidContributions} de ${goal.expectedContributions} esperadas`}
            />
          )}
        </div>
      )}
      <p className="mt-4 text-foot text-ink-2">Só entram as contribuições das famílias. As vendas das campanhas têm a página delas.</p>
    </section>
  );
}
