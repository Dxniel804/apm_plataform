"use client";

import { useEffect, useState } from "react";
import { QrCode, qrSvgFile } from "@/components/portal/QrCode";
import { Button } from "@/components/ui/Button";
import { CheckboxField } from "@/components/ui/CheckboxField";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { TextAreaField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiError, ApiResult, PublicLink, SchoolSettings } from "@/lib/api/types";
import { saveBlob } from "@/lib/download";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { areasFor } from "@/lib/permissions";

const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi alterado.";

function describe(error: ApiError, fallback = "Não foi possível salvar. Tente de novo."): { general: string | null; fields: Record<string, string> } {
  if (error.kind === "network" || error.kind === "timeout") return { general: NETWORK, fields: {} };
  if (error.kind === "problem" && error.status === 403) return { general: "Você não tem permissão para mudar as configurações.", fields: {} };
  if (error.kind === "problem" && error.code === "validation_error" && error.fields?.length) {
    const fields: Record<string, string> = {};
    for (const item of error.fields) fields[item.field] = item.code === "out_of_range" ? "Esse valor está fora do que a escola aceita." : "Confira este campo.";
    return { general: null, fields };
  }
  return { general: fallback, fields: {} };
}

const Card = ({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) => (
  <section className="rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-heading">{title}</h2>
      {action}
    </div>
    {children}
  </section>
);

/**
 * Configuracoes da escola: o link publico (com QR Code e cartaz), os valores que a familia ve e as metas do mes. So
 * quem tem `school_settings:manage` ve; a API confere de novo. O site nunca decide limite nem valor.
 */
export function SettingsArea({ schoolId, permissions }: { schoolId: string; permissions: string[] }) {
  const allowed = areasFor(permissions).manageSettings;
  const [version, setVersion] = useState(0);
  const key = `${schoolId}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; settings: ApiResult<SchoolSettings>; link: ApiResult<PublicLink> } | null>(null);
  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    void Promise.all([api.schoolSettings.get(schoolId), api.schoolSettings.publicLink(schoolId)]).then(([settings, link]) => {
      if (!cancelled) setLoaded({ key, settings, link });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, key, allowed]);

  if (!allowed) {
    return (
      <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
        O seu perfil não mexe nas configurações desta escola.
      </p>
    );
  }
  if (!loaded) {
    return (
      <div role="status" aria-busy="true">
        <span className="sr-only">Carregando as configurações…</span>
        <div aria-hidden="true" className="skeleton h-32 w-full" />
      </div>
    );
  }
  const { settings, link } = loaded;
  return (
    <div className="space-y-6">
      <p className="max-w-[62ch] text-body text-ink-2">O link da sua escola, os valores que as famílias veem e as metas do mês.</p>
      {link.ok ? <LinkCard schoolId={schoolId} link={link.data} /> : <p role="alert" className="text-sub font-medium text-bad">{describe(link.error).general}</p>}
      {settings.ok ? (
        <>
          <AmountsCard schoolId={schoolId} settings={settings.data} onSaved={() => setVersion((n) => n + 1)} />
          <GoalsCard schoolId={schoolId} settings={settings.data} onSaved={() => setVersion((n) => n + 1)} />
        </>
      ) : (
        <p role="alert" className="text-sub font-medium text-bad">{describe(settings.error).general}</p>
      )}
    </div>
  );
}

function LinkCard({ schoolId, link }: { schoolId: string; link: PublicLink }) {
  const [copied, setCopied] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setProblem("Não foi possível copiar. Selecione o endereço e copie à mão.");
    }
  }
  function downloadQr() {
    const svg = qrSvgFile(link.url);
    if (svg) saveBlob(new Blob([svg], { type: "image/svg+xml" }), `qr-${link.slug}.svg`);
  }
  async function poster() {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    const result = await api.schoolSettings.poster(schoolId);
    setBusy(false);
    if (!result.ok) return setProblem(describe(result.error, "Não foi possível gerar o cartaz agora.").general);
    saveBlob(result.data.blob, `cartaz-${link.slug}.pdf`);
  }

  return (
    <Card title="Link da escola">
      <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_11rem]">
        <div className="min-w-0 space-y-4">
          <p className="text-sub text-ink-2">É este o endereço que você passa para as famílias. Quem abre escolhe o valor e paga pelo Pix, e o dinheiro vai para a conta desta escola.</p>
          <p className="rounded-[var(--r-md)] bg-chip px-4 py-3 text-body font-medium text-brand-800 [overflow-wrap:anywhere]" data-testid="school-link">
            {link.url}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" size="md" onClick={() => void copy()} className="rounded-full!">
              {copied ? "Link copiado" : "Copiar link"}
            </Button>
            <Button variant="secondary" size="md" onClick={downloadQr} className="rounded-full!">
              Baixar o QR Code
            </Button>
            <Button size="md" onClick={() => void poster()} disabled={busy} aria-busy={busy} className="rounded-full!">
              {busy ? "Gerando o cartaz…" : "Baixar o cartaz (PDF)"}
            </Button>
          </div>
          <p className="text-foot text-ink-2">Confira o endereço antes de imprimir: depois que o cartaz está nas paredes, o endereço não pode mudar.</p>
          <div aria-live="polite">{problem && <p role="alert" className="text-sub font-medium text-bad">{problem}</p>}</div>
        </div>
        <QrCode payload={link.url} label={`QR Code do link da ${link.schoolName}. Aponte a câmera do celular para abrir a página.`} />
      </div>
    </Card>
  );
}

function AmountsCard({ schoolId, settings, onSaved }: { schoolId: string; settings: SchoolSettings; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [amounts, setAmounts] = useState<number[]>(settings.suggestedAmountsCents);
  const [custom, setCustom] = useState(settings.allowCustomAmount);
  const [text, setText] = useState(settings.freeAmountText ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function start() {
    setAmounts(settings.suggestedAmountsCents);
    setCustom(settings.allowCustomAmount);
    setText(settings.freeAmountText ?? "");
    setErrors({});
    setGeneral(null);
    setOpen(true);
  }
  async function save() {
    if (busy) return;
    const problems: Record<string, string> = {};
    const filled = amounts.filter((a) => a > 0);
    if (filled.length === 0) problems.suggested_amounts_cents = "Deixe pelo menos um valor sugerido.";
    else if (filled.some((a) => a < settings.minContributionCents || a > settings.maxContributionCents))
      problems.suggested_amounts_cents = `Cada valor vai de ${formatBRL(settings.minContributionCents)} a ${formatBRL(settings.maxContributionCents)}.`;
    else if (new Set(filled).size !== filled.length) problems.suggested_amounts_cents = "Não repita o mesmo valor.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    const result = await api.schoolSettings.update(schoolId, { suggestedAmountsCents: filled, allowCustomAmount: custom, freeAmountText: text.trim() || null });
    setBusy(false);
    if (!result.ok) {
      const d = describe(result.error);
      setErrors(d.fields);
      return setGeneral(d.general);
    }
    setOpen(false);
    onSaved();
  }

  return (
    <Card title="Valores da contribuição" action={<Button variant="secondary" size="md" onClick={start} className="rounded-full!">Editar</Button>}>
      <dl className="space-y-3 text-sub">
        <div>
          <dt className="text-ink-2">Valores sugeridos</dt>
          <dd className="font-semibold text-brand-800">{settings.suggestedAmountsCents.map(formatBRL).join(" · ")}</dd>
        </div>
        <div>
          <dt className="text-ink-2">Outro valor</dt>
          <dd>{settings.allowCustomAmount ? `A família pode digitar outro valor (de ${formatBRL(settings.minContributionCents)} a ${formatBRL(settings.maxContributionCents)}).` : "Só os valores sugeridos."}</dd>
        </div>
        <div>
          <dt className="text-ink-2">Texto ao lado do valor livre</dt>
          <dd className="[overflow-wrap:anywhere]">{settings.freeAmountText ?? "Nenhum."}</dd>
        </div>
      </dl>
      <FormModal open={open} title="Valores da contribuição" intro="Os valores que a família vê na página da escola." onClose={() => setOpen(false)} busy={busy}>
        <form method="post" noValidate aria-label="Valores da contribuição" onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-5">
          <fieldset className="space-y-3">
            <legend className="mb-1 text-sub font-semibold text-ink">Valores sugeridos (até 6)</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              {Array.from({ length: 6 }, (_, i) => (
                <TextField
                  key={i}
                  label={`Valor ${i + 1}`}
                  name={`amount-${i}`}
                  prefix="R$"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="0,00"
                  value={(amounts[i] ?? 0) === 0 ? "" : formatBRLNumber(amounts[i]!)}
                  onChange={(e) => setAmounts((prev) => Object.assign([...prev, ...Array(6).fill(0)].slice(0, 6), { [i]: centsFromDigits(e.target.value) }))}
                />
              ))}
            </div>
            {errors.suggested_amounts_cents && <p role="alert" className="text-sub font-medium text-bad">{errors.suggested_amounts_cents}</p>}
          </fieldset>
          <CheckboxField label="A família pode digitar outro valor" hint="Se desligar, só os valores sugeridos são aceitos." checked={custom} onChange={(e) => setCustom(e.target.checked)} />
          <TextAreaField label="Texto ao lado do valor livre" name="free-text" optional rows={2} maxLength={300} value={text} onChange={(e) => setText(e.target.value)} error={errors.free_amount_text} />
          <div aria-live="polite">{general && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{general}</p>}</div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Salvar valores" pendingLabel="Salvando…" pending={busy} />
        </form>
      </FormModal>
    </Card>
  );
}

function GoalsCard({ schoolId, settings, onSaved }: { schoolId: string; settings: SchoolSettings; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [goal, setGoal] = useState(settings.monthlyGoalCents ?? 0);
  const [expected, setExpected] = useState(settings.expectedContributions === null ? "" : String(settings.expectedContributions));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function start() {
    setGoal(settings.monthlyGoalCents ?? 0);
    setExpected(settings.expectedContributions === null ? "" : String(settings.expectedContributions));
    setErrors({});
    setGeneral(null);
    setOpen(true);
  }
  async function save() {
    if (busy) return;
    const count = expected.trim() === "" ? null : Number(expected);
    const problems: Record<string, string> = {};
    if (goal !== 0 && goal < 100) problems.monthly_goal_cents = "A meta vai de R$ 1,00 para cima.";
    if (count !== null && (!Number.isInteger(count) || count < 1 || count > 100000)) problems.expected_contributions = "Informe de 1 a 100.000 contribuições.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    const result = await api.schoolSettings.update(schoolId, { monthlyGoalCents: goal === 0 ? null : goal, expectedContributions: count });
    setBusy(false);
    if (!result.ok) {
      const d = describe(result.error);
      setErrors(d.fields);
      return setGeneral(d.general);
    }
    setOpen(false);
    onSaved();
  }

  return (
    <Card title="Metas do mês" action={<Button variant="secondary" size="md" onClick={start} className="rounded-full!">Editar</Button>}>
      <dl className="grid gap-3 text-sub sm:grid-cols-2">
        <div>
          <dt className="text-ink-2">Meta de arrecadação</dt>
          <dd className="font-semibold text-brand-800">{settings.monthlyGoalCents === null ? "Não definida" : formatBRL(settings.monthlyGoalCents)}</dd>
        </div>
        <div>
          <dt className="text-ink-2">Contribuições esperadas</dt>
          <dd className="font-semibold text-brand-800">{settings.expectedContributions === null ? "Não definido" : settings.expectedContributions}</dd>
        </div>
      </dl>
      <p className="mt-3 text-foot text-ink-2">Aparecem no painel como &ldquo;meta e adesão&rdquo;. São só uma referência: não mexem no caixa.</p>
      <FormModal open={open} title="Metas do mês" intro="O quanto a escola espera arrecadar e quantas contribuições." onClose={() => setOpen(false)} busy={busy}>
        <form method="post" noValidate aria-label="Metas do mês" onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-5">
          <TextField label="Meta de arrecadação do mês" optional name="goal" prefix="R$" inputMode="numeric" autoComplete="off" placeholder="Sem meta" value={goal === 0 ? "" : formatBRLNumber(goal)} onChange={(e) => setGoal(centsFromDigits(e.target.value))} error={errors.monthly_goal_cents} />
          <TextField label="Contribuições esperadas no mês" optional name="expected" inputMode="numeric" autoComplete="off" placeholder="Sem número" value={expected} onChange={(e) => setExpected(e.target.value.replace(/\D/g, "").slice(0, 6))} error={errors.expected_contributions} />
          <div aria-live="polite">{general && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{general}</p>}</div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Salvar metas" pendingLabel="Salvando…" pending={busy} />
        </form>
      </FormModal>
    </Card>
  );
}
