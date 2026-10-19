"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiError, ApiResult } from "@/lib/api/types";
import type { DueRoll, TaxApplies, TaxGuide, TaxKind, TaxMonth, TaxPreview, TaxRule, TaxRules, TaxSuggestion } from "@/lib/api/tax";
import { formatDateLong, formatDayLong } from "@/lib/format";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { currentLocalPeriod, periodLabel, recentPeriods } from "@/lib/statement-labels";

const KIND_LABELS: Record<TaxKind, string> = { IRRF: "Imposto de renda (IRRF)", INSS: "INSS", ISS: "ISS (prefeitura)", OTHER: "Outro" };
const APPLIES_LABELS: Record<TaxApplies, string> = { PF: "Só pessoa física", PJ: "Só empresa", BOTH: "Pessoa física e empresa" };

/** 150 pontos-base viram "1,5%"; o usuario digita em porcentagem. */
const percentText = (bps: number) => (bps / 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const bpsFromText = (text: string): number | null => {
  const n = Number(text.replace(/\s/g, "").replace(",", "."));
  const bps = Math.round(n * 100);
  return Number.isFinite(n) && bps >= 1 && bps <= 10000 ? bps : null;
};

function describe(error: ApiError): string {
  if (error.kind === "network" || error.kind === "timeout") return "Não foi possível falar com o servidor. Nada foi alterado.";
  if (error.code === "rule_does_not_apply") return "Esta regra não vale para este tipo de prestador.";
  if (error.status === 403) return "O seu perfil não mexe nos impostos.";
  if (error.status === 404) return "Isto não está mais aqui. Atualize a página.";
  if (error.status === 422) return "Confira os dados: o código da guia tem 4 números, o dia do vencimento vai de 1 a 31 e é preciso dizer o código ou como pagar.";
  return "Não foi possível concluir. Tente de novo.";
}

function Money({ label, cents, onChange, hint }: { label: string; cents: number; onChange: (v: number) => void; hint?: string }) {
  return <TextField label={label} name={label} prefix="R$" inputMode="numeric" autoComplete="off" placeholder="0,00" hint={hint} value={cents === 0 ? "" : formatBRLNumber(cents)} onChange={(e) => onChange(centsFromDigits(e.target.value))} />;
}

// --- rules ---------------------------------------------------------------------------------------

interface RuleDraft {
  ruleKey: string;
  label: string;
  taxKind: TaxKind;
  appliesTo: TaxApplies;
  rate: string;
  capCents: number;
  minCents: number;
  darfCode: string;
  howto: string;
  dueDay: string;
  dueRoll: DueRoll;
  sourceNote: string;
}

function draftOf(rule: TaxRule | null, suggestion: TaxSuggestion | null): RuleDraft {
  if (rule)
    return { ruleKey: rule.ruleKey, label: rule.label, taxKind: rule.taxKind, appliesTo: rule.appliesTo, rate: percentText(rule.rateBps), capCents: rule.baseCapCents ?? 0, minCents: rule.minTotalCents, darfCode: rule.darfCode ?? "", howto: rule.howto ?? "", dueDay: String(rule.dueDay), dueRoll: rule.dueRoll, sourceNote: rule.sourceNote ?? "" };
  if (suggestion)
    return { ruleKey: suggestion.ruleKey, label: suggestion.label, taxKind: suggestion.taxKind, appliesTo: suggestion.appliesTo, rate: suggestion.rateBps === null ? "" : percentText(suggestion.rateBps), capCents: suggestion.baseCapCents ?? 0, minCents: 1000, darfCode: suggestion.darfCode ?? "", howto: suggestion.howto ?? "", dueDay: "", dueRoll: "PREVIOUS", sourceNote: "" };
  return { ruleKey: "", label: "", taxKind: "IRRF", appliesTo: "PJ", rate: "", capCents: 0, minCents: 1000, darfCode: "", howto: "", dueDay: "", dueRoll: "PREVIOUS", sourceNote: "" };
}

function RuleModal({ schoolId, rule, suggestion, onClose, onDone }: { schoolId: string; rule: TaxRule | null; suggestion: TaxSuggestion | null; onClose: () => void; onDone: () => void }) {
  const [d, setD] = useState(() => draftOf(rule, suggestion));
  const [validated, setValidated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof RuleDraft>(key: K, value: RuleDraft[K]) => setD((prev) => ({ ...prev, [key]: value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const rateBps = bpsFromText(d.rate);
    const dueDay = Number(d.dueDay);
    if (!/^[a-z0-9][a-z0-9-]{2,39}$/.test(d.ruleKey)) return setError("O código interno usa letras minúsculas, números e hífen (de 3 a 40 caracteres).");
    if (d.label.trim() === "") return setError("Dê um nome à regra.");
    if (rateBps === null) return setError("Informe a alíquota em porcentagem, por exemplo 1,5.");
    if (!Number.isInteger(dueDay) || dueDay < 1 || dueDay > 31) return setError("Informe o dia do vencimento, de 1 a 31.");
    if (d.darfCode.trim() === "" && d.howto.trim() === "") return setError("Diga o código da guia ou como ela é paga.");
    setBusy(true);
    setError(null);
    const r = await api.tax.saveRule(schoolId, {
      ruleKey: d.ruleKey,
      label: d.label.trim(),
      taxKind: d.taxKind,
      appliesTo: d.appliesTo,
      rateBps,
      ...(d.capCents > 0 ? { baseCapCents: d.capCents } : {}),
      minTotalCents: d.minCents,
      ...(d.darfCode.trim() ? { darfCode: d.darfCode.trim() } : {}),
      ...(d.howto.trim() ? { howto: d.howto.trim() } : {}),
      dueDay,
      dueRoll: d.dueRoll,
      ...(d.sourceNote.trim() ? { sourceNote: d.sourceNote.trim() } : {}),
      validated,
    });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onDone();
  }

  return (
    <FormModal title={rule ? "Mudar a regra" : "Nova regra"} intro="A regra diz como calcular e onde pagar. O sistema não sabe a lei: o que você escreve aqui é o que ele usa." onClose={onClose} busy={busy}>
      <form method="post" onSubmit={(e) => void submit(e)} className="space-y-5">
        {suggestion && <p className="rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">{suggestion.warning}</p>}
        <TextField label="Nome da regra" name="label" maxLength={80} value={d.label} onChange={(e) => set("label", e.target.value)} />
        <TextField label="Código interno" name="rule-key" maxLength={40} hint="Letras minúsculas, números e hífen. Uma mudança com o mesmo código vira uma nova versão da regra." value={d.ruleKey} onChange={(e) => set("ruleKey", e.target.value)} disabled={rule !== null} />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField id="rule-kind" label="Imposto" value={d.taxKind} onChange={(e) => set("taxKind", e.target.value as TaxKind)}>
            {(Object.keys(KIND_LABELS) as TaxKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </SelectField>
          <SelectField id="rule-applies" label="Vale para" value={d.appliesTo} onChange={(e) => set("appliesTo", e.target.value as TaxApplies)}>
            {(Object.keys(APPLIES_LABELS) as TaxApplies[]).map((k) => (
              <option key={k} value={k}>
                {APPLIES_LABELS[k]}
              </option>
            ))}
          </SelectField>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Alíquota (%)" name="rate" inputMode="decimal" autoComplete="off" placeholder="1,5" value={d.rate} onChange={(e) => set("rate", e.target.value)} />
          <Money label="Limite da base (teto)" cents={d.capCents} onChange={(v) => set("capCents", v)} hint="Deixe em branco se não houver limite." />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Código da guia (4 números)" optional name="darf-code" inputMode="numeric" maxLength={4} value={d.darfCode} onChange={(e) => set("darfCode", e.target.value)} />
          <Money label="Valor mínimo da guia" cents={d.minCents} onChange={(v) => set("minCents", v)} hint="Abaixo disso a guia não se paga: soma-se ao mês seguinte." />
        </div>
        <TextField label="Ou como pagar" optional name="howto" maxLength={300} hint="Para o que não tem código da Receita: a prefeitura, o eSocial…" value={d.howto} onChange={(e) => set("howto", e.target.value)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Dia do vencimento (no mês seguinte)" name="due-day" inputMode="numeric" maxLength={2} value={d.dueDay} onChange={(e) => set("dueDay", e.target.value)} />
          <SelectField id="rule-roll" label="Se cair em fim de semana" value={d.dueRoll} onChange={(e) => set("dueRoll", e.target.value as DueRoll)}>
            <option value="PREVIOUS">Pagar no dia útil anterior</option>
            <option value="NEXT">Pagar no dia útil seguinte</option>
          </SelectField>
        </div>
        <TextField label="De onde vem esta regra" optional name="source" maxLength={200} hint="Exemplo: contadora Ana, 19/10, por e-mail." value={d.sourceNote} onChange={(e) => set("sourceNote", e.target.value)} />
        <label className="flex items-start gap-3 text-sub">
          <input type="checkbox" checked={validated} onChange={(e) => setValidated(e.target.checked)} className="mt-1 size-5" />
          <span>A contadora confirmou esta regra. Só marque se for verdade: o que ficar sem marcar aparece como &quot;não validada&quot;.</span>
        </label>
        <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
        <FormButtons onCancel={onClose} submitLabel="Salvar a regra" pending={busy} />
      </form>
    </FormModal>
  );
}

// --- a retention ---------------------------------------------------------------------------------

function RetentionModal({ schoolId, rules, period, onClose, onDone }: { schoolId: string; rules: TaxRule[]; period: string; onClose: () => void; onDone: () => void }) {
  const [ruleId, setRuleId] = useState(rules[0]?.id ?? "");
  const rule = rules.find((r) => r.id === ruleId);
  const [kind, setKind] = useState<"PF" | "PJ">(rule?.appliesTo === "PF" ? "PF" : "PJ");
  const [name, setName] = useState("");
  const [cents, setCents] = useState(0);
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<TaxPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!ruleId || cents <= 0 || (rule && rule.appliesTo !== "BOTH" && rule.appliesTo !== kind)) {
      void Promise.resolve().then(() => !cancelled && setPreview(null));
    } else {
      void api.tax.preview(schoolId, ruleId, kind, cents).then((r) => !cancelled && setPreview(r.ok ? r.data : null));
    }
    return () => {
      cancelled = true;
    };
  }, [schoolId, ruleId, kind, cents, rule]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ruleId) return setError("Escolha a regra.");
    if (name.trim() === "" || cents <= 0) return setError("Informe quem recebeu e o valor do serviço.");
    setBusy(true);
    setError(null);
    const r = await api.tax.addRetention(schoolId, { ruleId, providerKind: kind, providerName: name.trim(), competence: period, grossCents: cents, ...(note.trim() ? { note: note.trim() } : {}) });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    onDone();
  }

  return (
    <FormModal title="Registrar uma retenção" intro={`Serviço pago em ${periodLabel(period)}. O valor retido é calculado pela regra escolhida.`} onClose={onClose} busy={busy}>
      <form method="post" onSubmit={(e) => void submit(e)} className="space-y-5">
        <SelectField id="ret-rule" label="Regra" value={ruleId} onChange={(e) => setRuleId(e.target.value)}>
          {rules.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
              {r.validated ? "" : " (não validada)"}
            </option>
          ))}
        </SelectField>
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField id="ret-kind" label="Quem recebeu" value={kind} onChange={(e) => setKind(e.target.value as "PF" | "PJ")}>
            <option value="PJ">Empresa</option>
            <option value="PF">Pessoa física (autônomo)</option>
          </SelectField>
          <TextField label="Nome de quem recebeu" name="provider" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Money label="Valor do serviço (bruto)" cents={cents} onChange={setCents} />
        {preview && (
          <p role="status" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-brand-800">
            Retido: <strong>{formatBRL(preview.retainedCents)}</strong> · pago a quem prestou o serviço: <strong>{formatBRL(preview.netCents)}</strong>
            {preview.baseCents !== cents ? ` · base limitada a ${formatBRL(preview.baseCents)}` : ""}
          </p>
        )}
        <TextField label="Observação" optional name="note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
        <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>
        <FormButtons onCancel={onClose} submitLabel="Registrar" pending={busy} />
      </form>
    </FormModal>
  );
}

// --- the guide: what to type on the site of the Receita --------------------------------------------

function Cola({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-4 py-3">
      <dt className="text-sub text-ink-2">{label}</dt>
      <dd className="mt-0.5 text-[1.125rem] font-bold tabular-nums text-brand-800 [overflow-wrap:anywhere]">{value}</dd>
    </div>
  );
}

function GuideCard({ guide: g }: { guide: TaxGuide }) {
  return (
    <li className="overflow-hidden rounded-[var(--r-lg)] border border-line bg-white" data-testid={`guide-${g.ruleKey}`}>
      <div className="px-5 py-4 sm:px-6">
        <p className="text-[1.0625rem] font-semibold text-brand-800">{g.label}</p>
        <p className="text-sub text-ink-2">
          {KIND_LABELS[g.taxKind]} · {g.count === 1 ? "1 retenção" : `${g.count} retenções`} em {periodLabel(g.competence)}
        </p>
      </div>
      {!g.validated && (
        <p role="note" className="mx-5 mb-3 rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn sm:mx-6">
          <strong>A regra ainda não foi validada pela contadora.</strong> Não pague com base neste valor sem conferir com ela.
        </p>
      )}
      {g.mixedVersions && <p className="mx-5 mb-3 rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-brand-800 sm:mx-6">Este mês tem retenções calculadas com versões diferentes da regra.</p>}
      <dl className="grid divide-y divide-line border-t border-line sm:grid-cols-2 sm:divide-y-0 sm:[&>div:nth-child(even)]:border-l sm:[&>div:nth-child(n+3)]:border-t sm:[&>div]:border-line">
        <Cola label="Valor a pagar" value={formatBRL(g.totalCents)} />
        <Cola label="Vencimento" value={formatDayLong(g.dueDate)} />
        {g.darfCode && <Cola label="Código da receita" value={g.darfCode} />}
        <Cola label="Período de apuração" value={periodLabel(g.competence)} />
      </dl>
      <div className="space-y-3 border-t border-line px-5 py-4 sm:px-6">
        {g.belowMinimum && (
          <p className="rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
            O valor está abaixo do mínimo de {formatBRL(g.minTotalCents)} da guia: não se paga agora. Some ao do mês seguinte.
          </p>
        )}
        {g.howto && <p className="text-sub">{g.howto}</p>}
        {g.siteUrl && (
          <a href={g.siteUrl} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center rounded-full border border-line-strong bg-white px-5 text-sub font-semibold text-brand-800 hover:bg-bg">
            Abrir o site da Receita (cálculo da guia)
          </a>
        )}
        <p className="text-foot text-ink-2">Os feriados não são considerados no vencimento: confira o calendário. Depois de pagar, registre a saída em Despesas, na categoria &quot;Impostos retidos e tributos pagos&quot;.</p>
      </div>
    </li>
  );
}

// --- the area ------------------------------------------------------------------------------------

interface Props {
  schoolId: string;
}

/**
 * Impostos retidos (docs/tax-guides.md). A escola, com a contadora, escreve as regras; aqui se registra o que foi
 * retido de cada serviço pago e se vê, por imposto e por mês, a "cola": o valor, o código, o período e o vencimento
 * para digitar no site da Receita. O sistema não fala com o governo e não decide a lei: uma regra só aparece como
 * validada se alguém disse que a contadora confirmou.
 */
export function TaxArea({ schoolId }: Props) {
  const [latest] = useState(() => currentLocalPeriod());
  const options = recentPeriods(latest, 36);
  const [period, setPeriod] = useState(options[0]!);
  const [version, setVersion] = useState(0);
  const [rules, setRules] = useState<ApiResult<TaxRules> | null>(null);
  const [month, setMonth] = useState<{ period: string; res: ApiResult<TaxMonth> } | null>(null);
  const [editing, setEditing] = useState<{ rule: TaxRule | null; suggestion: TaxSuggestion | null } | null>(null);
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.tax.rules(schoolId).then((res) => !cancelled && setRules(res));
    void api.tax.month(schoolId, period).then((res) => !cancelled && setMonth({ period, res }));
    return () => {
      cancelled = true;
    };
  }, [schoolId, period, version]);

  const m = month?.period === period ? month.res : null;
  const refresh = () => setVersion((n) => n + 1);

  async function voidRetention(id: string) {
    setError(null);
    const r = await api.tax.voidRetention(schoolId, id);
    if (!r.ok) return setError(describe(r.error));
    refresh();
  }

  return (
    <div className="space-y-8">
      <section aria-label="Regras" className="rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
        <h2 className="text-heading">Regras</h2>
        <p className="mt-1 max-w-[64ch] text-sub text-ink-2">
          O sistema não fala com a Receita e não sabe a lei. Você, com a contadora, escreve como cada imposto é calculado e onde se paga; ele guarda o que foi retido, soma por mês e mostra o que digitar no site do governo.
        </p>
        {rules && !rules.ok && <p className="mt-3 text-sub text-ink-2">Não foi possível carregar as regras.</p>}
        {rules && rules.ok && (
          <>
            {rules.data.rules.length === 0 && <p className="mt-4 text-sub">Nenhuma regra ainda. Comece por uma sugestão abaixo (não validada) ou crie a sua.</p>}
            <ul aria-label="Regras da escola" className="mt-4 space-y-3">
              {rules.data.rules.map((r) => (
                <li key={r.id} className="rounded-[var(--r-md)] border border-line px-4 py-3">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="font-semibold">{r.label}</p>
                      <p className="text-sub text-ink-2">
                        {KIND_LABELS[r.taxKind]} · {percentText(r.rateBps)}% · {APPLIES_LABELS[r.appliesTo]}
                        {r.darfCode ? ` · código ${r.darfCode}` : ""} · vence dia {r.dueDay}
                      </p>
                      <p className={`text-sub ${r.validated ? "text-ok" : "font-semibold text-warn"}`}>
                        {r.validated && r.validatedAt ? `Validada pela contadora (marcado em ${formatDateLong(r.validatedAt)})` : "Não validada pela contadora"}
                      </p>
                    </div>
                    <Button variant="chip" size="md" onClick={() => setEditing({ rule: r, suggestion: null })} aria-label={`Mudar a regra ${r.label}`} className="min-h-11">
                      Mudar
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button variant="chip" size="md" onClick={() => setEditing({ rule: null, suggestion: null })} className="min-h-11">
                Nova regra
              </Button>
              {rules.data.suggestions
                .filter((s) => !rules.data.rules.some((r) => r.ruleKey === s.ruleKey))
                .map((s) => (
                  <Button key={s.ruleKey} variant="plain" size="md" onClick={() => setEditing({ rule: null, suggestion: s })} className="min-h-11 rounded-full!">
                    Sugestão: {s.label}
                  </Button>
                ))}
            </div>
          </>
        )}
      </section>

      <section aria-label="Mês" className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-0 basis-56">
            <SelectField id="tax-period" label="Mês do serviço" value={period} onChange={(e) => setPeriod(e.target.value)}>
              {options.map((p) => (
                <option key={p} value={p}>
                  {periodLabel(p)}
                </option>
              ))}
            </SelectField>
          </div>
          {rules && rules.ok && rules.data.rules.length > 0 && (
            <Button variant="chip" size="md" onClick={() => setRegistering(true)} className="min-h-11">
              Registrar uma retenção
            </Button>
          )}
        </div>
        <div aria-live="polite">{error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}</div>

        {!m && (
          <p role="status" aria-busy="true" className="text-sub text-ink-2">
            Carregando…
          </p>
        )}
        {m && !m.ok && <p className="text-sub text-ink-2">{describe(m.error)}</p>}
        {m && m.ok && (
          <>
            <h2 className="text-heading">Guias de {periodLabel(period)}</h2>
            {m.data.guides.length === 0 ? (
              <p className="text-sub text-ink-2">Nenhuma retenção neste mês, então não há guia a pagar.</p>
            ) : (
              <ul aria-label="Guias" className="space-y-4">
                {m.data.guides.map((g) => (
                  <GuideCard key={g.ruleKey} guide={g} />
                ))}
              </ul>
            )}
            <h2 className="pt-2 text-heading">Retenções de {periodLabel(period)}</h2>
            {m.data.retentions.length === 0 ? (
              <p className="text-sub text-ink-2">Nada registrado.</p>
            ) : (
              <ul aria-label="Retenções" className="space-y-3">
                {m.data.retentions.map((r) => (
                  <li key={r.id} className={`rounded-[var(--r-md)] border border-line bg-white px-4 py-3 ${r.voided ? "opacity-60" : ""}`}>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                      <div className="min-w-0 flex-1 basis-56">
                        <p className="font-semibold [overflow-wrap:anywhere]">
                          {r.providerName} {r.voided ? "(anulada)" : ""}
                        </p>
                        <p className="text-sub text-ink-2">
                          {r.ruleLabel} · {r.providerKind === "PF" ? "pessoa física" : "empresa"} · serviço {formatBRL(r.grossCents)}
                        </p>
                        <p className="text-sub">
                          Retido <strong className="tabular-nums">{formatBRL(r.retainedCents)}</strong> · pago ao prestador <span className="tabular-nums">{formatBRL(r.netCents)}</span>
                        </p>
                      </div>
                      {!r.voided && (
                        <Button variant="plain" size="md" onClick={() => void voidRetention(r.id)} aria-label={`Anular a retenção de ${r.providerName}`} className="rounded-full!">
                          Anular
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      {editing && (
        <RuleModal
          schoolId={schoolId}
          rule={editing.rule}
          suggestion={editing.suggestion}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            refresh();
          }}
        />
      )}
      {registering && rules && rules.ok && (
        <RetentionModal
          schoolId={schoolId}
          rules={rules.data.rules}
          period={period}
          onClose={() => setRegistering(false)}
          onDone={() => {
            setRegistering(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}
