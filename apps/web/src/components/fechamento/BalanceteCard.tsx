"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import { balancetePdfHref, type Balancete, type BalancetePlace } from "@/lib/api/balancete";
import type { ApiError, ApiResult } from "@/lib/api/types";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { currentLocalPeriod, periodLabel, recentPeriods } from "@/lib/statement-labels";

const link = "inline-flex min-h-11 items-center rounded-full border border-line-strong bg-white px-5 text-sub font-semibold text-brand-800 hover:bg-bg";

function describe(error: ApiError): string {
  if (error.status === 403) return "O seu perfil não pode fazer isso.";
  if (error.status === 422) return "Confira os valores digitados.";
  if (error.status === 409) return "O livro caixa mudou enquanto a folha era montada. Tente de novo.";
  return "Não foi possível agora. Tente de novo em instantes.";
}

function Line({ label, cents, strong }: { label: string; cents: number; strong?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-4 border-b border-line py-1.5 ${strong ? "font-bold text-brand-800" : ""}`}>
      <dt className="text-sub">{label}</dt>
      <dd className="tabular-nums text-sub">{formatBRL(cents)}</dd>
    </div>
  );
}

function Group({ title, lines, total, totalLabel }: { title: string; lines: { name: string; cents: number }[]; total: number; totalLabel: string }) {
  return (
    <section aria-label={title} className="mt-4">
      <h3 className="rounded-[var(--r-md)] bg-bg px-3 py-1.5 text-center text-sub font-bold text-brand-800">{title}</h3>
      <dl>
        {lines.length === 0 && <Line label="Nenhum lançamento no mês" cents={0} />}
        {lines.map((l) => (
          <Line key={l.name} label={l.name} cents={l.cents} />
        ))}
        <Line label={totalLabel} cents={total} strong />
      </dl>
    </section>
  );
}

function Places({ title, place, labels }: { title: string; place: BalancetePlace; labels: [string, string, string, string] }) {
  return (
    <section aria-label={title} className="mt-4">
      <h3 className="rounded-[var(--r-md)] bg-bg px-3 py-1.5 text-center text-sub font-bold text-brand-800">{title}</h3>
      <dl>
        <Line label={labels[0]} cents={place.cashCents} />
        <Line label={labels[1]} cents={place.bankCents} />
        <Line label={labels[2]} cents={place.investmentCents} />
        <Line label={labels[3]} cents={place.totalCents} strong />
      </dl>
    </section>
  );
}

function Money({ label, hint, cents, onChange }: { label: string; hint?: string; cents: number; onChange: (v: number) => void }) {
  return (
    <TextField
      label={label}
      name={label}
      prefix="R$"
      inputMode="numeric"
      autoComplete="off"
      placeholder="0,00"
      hint={hint}
      value={cents === 0 ? "" : formatBRLNumber(cents)}
      onChange={(e) => onChange(centsFromDigits(e.target.value))}
    />
  );
}

interface Props {
  schoolId: string;
  /** `months:close`: quem digita o caixa, a aplicacao e o saldo da implantacao. */
  canType: boolean;
}

/**
 * O balancete do mes no formato da folha da contadora, para a conferencia mensal: a escola poe a dela ao lado
 * da folha da contabilidade e cada linha ou bate ou mostra onde olhar. Os numeros sao os do livro caixa (a API
 * os confere contra o resumo); o que o livro nao sabe e digitado: o saldo de quando a escola comecou, e o caixa
 * e a aplicacao do fim de cada mes. O banco e o que sobra do total.
 */
export function BalanceteCard({ schoolId, canType }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const options = recentPeriods(latest, 36);
  const [period, setPeriod] = useState(options[0]!);
  const [version, setVersion] = useState(0);
  const key = `${schoolId}|${period}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<Balancete> } | null>(null);
  const [cash, setCash] = useState(0);
  const [invested, setInvested] = useState(0);
  const [startBank, setStartBank] = useState(0);
  const [startCash, setStartCash] = useState(0);
  const [startInvested, setStartInvested] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.balancete.get(schoolId, period).then((res) => {
      if (cancelled) return;
      setLoaded({ key, res });
      if (res.ok) {
        setCash(res.data.closing.cashCents);
        setInvested(res.data.closing.investmentCents);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, key]);

  const res = loaded?.key === key ? loaded.res : null;

  async function saveMonth() {
    setBusy(true);
    setError(null);
    setNotice(null);
    const r = await api.balancete.set(schoolId, { kind: "MONTH", period, cashCents: cash, investmentCents: invested });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    setNotice(`Caixa e aplicação de ${periodLabel(period)} salvos.`);
    setVersion((n) => n + 1);
  }

  async function saveStart() {
    setBusy(true);
    setError(null);
    setNotice(null);
    const r = await api.balancete.set(schoolId, { kind: "OPENING", bankCents: startBank, cashCents: startCash, investmentCents: startInvested });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    setNotice("Saldo de quando a escola começou salvo.");
    setVersion((n) => n + 1);
  }

  return (
    <section aria-label="Balancete do mês" className="mb-8 rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
      <h2 className="text-heading">Balancete do mês</h2>
      <p className="mt-1 max-w-[62ch] text-sub text-ink-2">
        A mesma folha que a contadora entrega, feita a partir do livro caixa. Todo mês, ponha a sua ao lado da dela: cada linha ou bate, ou mostra onde olhar.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <div className="min-w-0 basis-56">
          <SelectField id="balancete-period" label="Mês" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {options.map((p) => (
              <option key={p} value={p}>
                {periodLabel(p)}
              </option>
            ))}
          </SelectField>
        </div>
        <a className={link} href={balancetePdfHref(schoolId, period)} download>
          Balancete (PDF, com assinaturas)
        </a>
      </div>

      {!res && (
        <p role="status" aria-busy="true" className="mt-4 text-sub text-ink-2">
          Montando o balancete…
        </p>
      )}
      {res && !res.ok && (
        <p className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {describe(res.error)}
        </p>
      )}
      {res && res.ok && (
        <div className="mt-2 max-w-xl" data-testid="balancete">
          <Places title="Saldo anterior" place={res.data.opening} labels={["Caixa", "Banco c/ movimento", "Em aplicação", "Total em caixa"]} />
          <Group title="Receitas" lines={res.data.revenue} total={res.data.totalRevenueCents} totalLabel="Total de receitas" />
          <Group title="(-) Bens permanentes" lines={res.data.capital} total={res.data.totalCapitalCents} totalLabel="Total de bens permanentes" />
          <Group title="(-) Despesas" lines={res.data.expenses} total={res.data.totalExpensesCents} totalLabel="Total das despesas" />
          <dl className="mt-4">
            <Line label="Saldo do mês" cents={res.data.balanceOfMonthCents} strong />
          </dl>
          <Places title="Demonstração do saldo final" place={res.data.closing} labels={["Em caixa", "Em banco", "Em aplicação", "Saldo final"]} />
          {!res.data.closingTyped && (
            <p className="mt-3 rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-brand-800">
              Caixa e aplicação deste mês ainda não foram informados: o que não está nelas aparece em banco.
            </p>
          )}
          {!res.data.hasOpening && (
            <p className="mt-3 rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-brand-800">
              O saldo de quando a escola começou a usar o sistema ainda não foi informado. Sem ele, os saldos aqui partem de zero e não vão bater com o banco.
            </p>
          )}
          {res.data.closing.bankCents < 0 && (
            <p role="alert" className="mt-3 rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
              O banco ficou negativo: confira o caixa e a aplicação digitados.
            </p>
          )}
        </div>
      )}

      {canType && (
        <div className="mt-6 space-y-6 border-t border-line pt-6">
          <form
            method="post"
            onSubmit={(e) => {
              e.preventDefault();
              void saveMonth();
            }}
            className="space-y-3"
          >
            <h3 className="text-sub font-bold text-brand-800">Onde está o dinheiro no fim de {periodLabel(period)}</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <Money label="Em caixa (dinheiro)" cents={cash} onChange={setCash} />
              <Money label="Em aplicação" hint="O banco é o que sobra do saldo total." cents={invested} onChange={setInvested} />
            </div>
            <Button type="submit" variant="plain" size="md" disabled={busy} className="rounded-full!">
              Salvar caixa e aplicação
            </Button>
          </form>

          <details className="rounded-[var(--r-md)] border border-line px-4 py-3">
            <summary className="cursor-pointer text-sub font-semibold text-brand-800">Saldo de quando a escola começou a usar o sistema</summary>
            <form
              method="post"
              onSubmit={(e) => {
                e.preventDefault();
                void saveStart();
              }}
              className="mt-3 space-y-3"
            >
              <p className="max-w-[62ch] text-sub text-ink-2">
                O livro caixa começa do zero. Digite uma vez o que a escola já tinha no dia em que começou: ele entra em todos os saldos.
              </p>
              <div className="grid gap-4 sm:grid-cols-3">
                <Money label="Em banco" cents={startBank} onChange={setStartBank} />
                <Money label="Em caixa" cents={startCash} onChange={setStartCash} />
                <Money label="Em aplicação" cents={startInvested} onChange={setStartInvested} />
              </div>
              <Button type="submit" variant="plain" size="md" disabled={busy} className="rounded-full!">
                Salvar saldo inicial
              </Button>
            </form>
          </details>
        </div>
      )}
      <div aria-live="polite">
        {error && <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}
        {notice && <p role="status" className="mt-4 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
      </div>
    </section>
  );
}
