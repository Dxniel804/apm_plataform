import { StatusPill } from "@/components/ui/StatusPill";
import type { PendingEntry, StatementEntry } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { KIND_LABELS } from "@/lib/status";
import { categoryLabel, entryStatus, formatLocalDateShort, pendingStatus } from "@/lib/statement-labels";

/**
 * O cartao das listas e o MESMO da rota Despesas (Figma): titulo em azul, uma linha de detalhes, o valor em
 * destaque e a situacao em pilula. Os lancamentos por tipo (contribuicoes, despesas, reembolsos, devolucoes)
 * e as pendencias usam este molde, entao a tesouraria le tudo do mesmo jeito.
 */
const CARD = "rounded-[var(--r-lg)] border border-line bg-white px-5 py-5 sm:px-8 sm:py-6";
const TITLE = "text-[1.0625rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere] sm:text-[1.25rem]";
const AMOUNT = "text-[1.25rem] font-bold tabular-nums text-brand-800 sm:text-[1.5rem]";

function EntryRow({ entry }: { entry: StatementEntry }) {
  const status = entryStatus(entry.kind, entry.status, entry.statusLabel);
  const counterparty =
    entry.beneficiaryLabel ?? entry.originLabel ?? (entry.kind === "CONTRIBUTION" ? "Contribuinte anônimo" : null);
  // O sentido (entrada ou saida) vem da API.
  const sign = entry.direction === "IN" ? "+" : "−";
  return (
    <li className={CARD}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="min-w-0 flex-1 basis-56">
          <p className={TITLE}>{entry.description ?? categoryLabel(entry.categoryKey)}</p>
          <p className="mt-1 text-sub text-ink-2 [overflow-wrap:anywhere]">
            <span className="font-medium text-ink">{KIND_LABELS[entry.kind]}</span>
            {counterparty ? ` · ${counterparty}` : ""} · {formatLocalDateShort(entry.localDate)} · nº {entry.referenceCode}
            {entry.lateAdjustment ? " · ajuste tardio" : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <p className={AMOUNT}>
            <span className="sr-only">{entry.direction === "IN" ? "Entrada de " : "Saída de "}</span>
            <span aria-hidden="true">{sign}</span> {formatBRL(entry.amountCents)}
          </p>
          <StatusPill tone={status.tone}>{status.label}</StatusPill>
          <p className="text-foot tabular-nums text-ink-2">
            <span className="sr-only">Saldo depois deste lançamento: </span>
            saldo {formatBRL(entry.runningBalanceCents)}
          </p>
        </div>
      </div>
    </li>
  );
}

export function StatementList({ entries, label }: { entries: StatementEntry[]; label: string }) {
  return (
    <ul aria-label={label} className="space-y-4">
      {entries.map((entry) => (
        <EntryRow key={entry.transactionId} entry={entry} />
      ))}
    </ul>
  );
}

export function PendingRows({ entries, label }: { entries: PendingEntry[]; label: string }) {
  return (
    <ul aria-label={label} className="space-y-3">
      {entries.map((entry) => (
        <li key={entry.transactionId} className="rounded-[var(--r-lg)] border border-line bg-white px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[1.0625rem] font-semibold leading-snug text-brand-800 sm:text-[1.125rem]">
                {KIND_LABELS[entry.kind]} nº {entry.referenceCode}
              </p>
              <p className="mt-0.5 text-sub text-ink-2">{pendingStatus(entry.status)}</p>
            </div>
            <p className="shrink-0 text-[1.125rem] font-bold tabular-nums text-brand-800 sm:text-[1.25rem]">
              <span className="sr-only">{entry.direction === "IN" ? "A receber: " : "A pagar: "}</span>
              {formatBRL(entry.amountCents)}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
