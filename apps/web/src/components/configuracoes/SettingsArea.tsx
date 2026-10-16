"use client";

import { useEffect, useState } from "react";
import { PasswordForm } from "@/components/conta/PasswordForm";
import { QrCode, qrSvgFile } from "@/components/portal/QrCode";
import { Button } from "@/components/ui/Button";
import { CheckboxField } from "@/components/ui/CheckboxField";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { TextAreaField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiError, ApiResult, PublicLink, SchoolIdentity, SchoolSettings } from "@/lib/api/types";
import { saveBlob } from "@/lib/download";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { areasFor } from "@/lib/permissions";

const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi alterado.";

function describe(error: ApiError, fallback = "Não foi possível salvar. Tente de novo."): { general: string | null; fields: Record<string, string> } {
  if (error.kind === "network" || error.kind === "timeout") return { general: NETWORK, fields: {} };
  if (error.kind === "problem" && error.status === 403)
    return {
      general: "Você não tem permissão para mudar as configurações.",
      fields: {},
    };
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
  // Grade: as configuracoes da escola na coluna larga e a senha numa coluna ao lado, sempre a vista ao abrir a pagina.
  // No celular a senha vem primeiro.
  return (
    <div className="space-y-6">
      {/* A frase fica ACIMA das duas colunas: assim o primeiro cartao da esquerda e o da senha comecam na mesma linha. */}
      {allowed && <p className="max-w-[62ch] text-body text-ink-2">O nome e o link da sua escola, os valores que as famílias veem e as metas do mês.</p>}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="order-2 min-w-0 space-y-6 lg:order-1">
          {allowed ? (
            <SchoolSettings schoolId={schoolId} />
          ) : (
            <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
              O seu perfil não mexe nas configurações desta escola. Ao lado você pode trocar a sua senha.
            </p>
          )}
        </div>
        <div className="order-1 lg:sticky lg:top-6 lg:order-2">
          <AccountSection />
        </div>
      </div>
    </div>
  );
}

/** A senha de quem esta logado: direto na pagina, sem janela. Vale para qualquer perfil. */
function AccountSection() {
  return (
    <section id="senha" aria-labelledby="senha-title" className="scroll-mt-6 rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
      <h2 id="senha-title" className="text-heading">
        Alterar senha
      </h2>
      <p className="mb-5 mt-1 max-w-[62ch] text-sub text-ink-2">Ao trocar, as outras sessões abertas com a sua conta são encerradas. Você continua conectado neste navegador.</p>
      <PasswordForm />
    </section>
  );
}

function SchoolSettings({ schoolId }: { schoolId: string }) {
  const [version, setVersion] = useState(0);
  const key = `${schoolId}|${version}`;
  const [loaded, setLoaded] = useState<{
    key: string;
    settings: ApiResult<SchoolSettings>;
    link: ApiResult<PublicLink>;
    identity: ApiResult<SchoolIdentity>;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void Promise.all([api.schoolSettings.get(schoolId), api.schoolSettings.publicLink(schoolId), api.schoolSettings.identity(schoolId)]).then(([settings, link, identity]) => {
      if (!cancelled) setLoaded({ key, settings, link, identity });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, key]);

  if (!loaded) {
    return (
      <div role="status" aria-busy="true">
        <span className="sr-only">Carregando as configurações…</span>
        <div aria-hidden="true" className="skeleton h-32 w-full" />
      </div>
    );
  }
  const { settings, link, identity } = loaded;
  return (
    <div className="space-y-6">
      {identity.ok && <IdentityCard schoolId={schoolId} identity={identity.data} onSaved={() => setVersion((n) => n + 1)} />}
      {link.ok ? (
        <LinkCard schoolId={schoolId} link={link.data} />
      ) : (
        <p role="alert" className="text-sub font-medium text-bad">
          {describe(link.error).general}
        </p>
      )}
      {settings.ok ? (
        <>
          <AmountsCard schoolId={schoolId} settings={settings.data} onSaved={() => setVersion((n) => n + 1)} />
          <GoalsCard schoolId={schoolId} settings={settings.data} onSaved={() => setVersion((n) => n + 1)} />
        </>
      ) : (
        <p role="alert" className="text-sub font-medium text-bad">
          {describe(settings.error).general}
        </p>
      )}
    </div>
  );
}

const dateBR = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

function identityProblem(error: ApiError): string {
  if (error.kind === "network" || error.kind === "timeout") return NETWORK;
  if (error.kind === "problem") {
    if (error.code === "slug_taken") return "Esse endereço já é de outra escola (ou já foi). Escolha outro.";
    if (error.code === "slug_reserved") return "Essa palavra é reservada pelo sistema. Escolha outro endereço.";
    if (error.code === "slug_change_locked") return "O endereço foi trocado há pouco tempo. Veja abaixo quando pode mudar de novo.";
    if (error.status === 403) return "Você não tem permissão para mudar o nome e o endereço da escola.";
    if (error.code === "validation_error") return "Confira o nome (2 a 120 letras) e o endereço (3 a 40 caracteres: letras minúsculas, números e hífen).";
    if (error.code === "link_check_failed") return "Não foi possível confirmar o novo endereço. Nada foi alterado.";
  }
  return "Não foi possível salvar. Tente de novo. Nada foi alterado.";
}

/**
 * O nome e o endereco da escola. O nome muda sempre; o endereco muda duas vezes sem espera e, da terceira em diante, 15 dias
 * depois da anterior. Os enderecos antigos continuam abrindo a escola (nunca vao para outra): quem decide tudo isso e o banco.
 */
function IdentityCard({ schoolId, identity, onSaved }: { schoolId: string; identity: SchoolIdentity; onSaved: () => void }) {
  const [name, setName] = useState(identity.name);
  const [slug, setSlug] = useState(identity.slug);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const origin = identity.url.slice(0, identity.url.lastIndexOf("/") + 1);
  const cleanSlug = slug.trim().toLowerCase();
  const slugChanged = cleanSlug !== identity.slug;
  const nameChanged = name.trim() !== identity.name;
  const locked = identity.slugLockedUntil !== null;
  const slugFormat = /^[a-z0-9]+(-[a-z0-9]+)*$/.test(cleanSlug) && cleanSlug.length >= 3 && cleanSlug.length <= 40;
  const slugError = slugChanged && !slugFormat ? "Use de 3 a 40 caracteres: letras minúsculas, números e hífen (sem espaço nem acento)." : undefined;
  const canSave = (nameChanged || (slugChanged && !locked && slugFormat)) && name.trim().length >= 2 && !busy;

  async function save() {
    if (!canSave) return;
    if (slugChanged && !confirming) {
      setConfirming(true);
      return;
    }
    setBusy(true);
    setProblem(null);
    setSaved(false);
    const result = await api.schoolSettings.updateIdentity(schoolId, {
      ...(nameChanged ? { name: name.trim() } : {}),
      ...(slugChanged ? { slug: cleanSlug } : {}),
    });
    setBusy(false);
    setConfirming(false);
    if (!result.ok) {
      setProblem(identityProblem(result.error));
      // O servidor e a verdade: a tela volta a perguntar o que resta das trocas.
      if (result.error.kind === "problem" && result.error.code === "slug_change_locked") onSaved();
      return;
    }
    setSaved(true);
    onSaved();
  }

  return (
    <Card title="Nome e endereço da escola">
      <div className="max-w-[40rem] space-y-4">
        <TextField
          label="Nome da escola"
          name="school-name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setSaved(false);
          }}
          maxLength={120}
          autoComplete="off"
        />
        <TextField
          label="Endereço do link"
          name="school-slug"
          value={slug}
          onChange={(e) => {
            setSlug(e.target.value);
            setConfirming(false);
            setSaved(false);
          }}
          disabled={locked}
          spellCheck={false}
          autoCapitalize="none"
          autoComplete="off"
          maxLength={40}
          error={slugError}
          hint={`Fica assim: ${origin}${cleanSlug || "…"}`}
        />
        {locked ? (
          <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
            O endereço foi trocado há pouco. Você poderá trocá-lo de novo em <strong>{dateBR(identity.slugLockedUntil as string)}</strong>. O nome pode mudar agora.
          </p>
        ) : (
          <p className="text-foot text-ink-2">
            {identity.freeChangesLeft > 0
              ? `Você ainda pode trocar o endereço ${identity.freeChangesLeft === 1 ? "mais 1 vez" : `mais ${identity.freeChangesLeft} vezes`} sem espera. Depois, só a cada 15 dias.`
              : "A partir daqui, o endereço só pode ser trocado a cada 15 dias."}
          </p>
        )}
        {identity.previousSlugs.length > 0 && (
          <p className="text-foot text-ink-2">Endereços antigos (continuam abrindo a escola, e nenhuma outra escola pode usá-los): {identity.previousSlugs.join(", ")}.</p>
        )}
        {!identity.linkActive && (
          <p role="note" className="rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
            O link só abre para as famílias depois que a conta de recebimento (Pix) da escola for cadastrada. Você já pode escolher o nome e o endereço.
          </p>
        )}
        {confirming && slugChanged && (
          <p role="alert" className="rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub text-warn">
            Trocar o endereço para{" "}
            <strong>
              {origin}
              {cleanSlug}
            </strong>
            ? O endereço antigo continua funcionando, mas conta como uma das trocas.
          </p>
        )}
        <div aria-live="polite">
          {problem && (
            <p role="alert" className="text-sub font-medium text-bad">
              {problem}
            </p>
          )}
          {saved && (
            <p role="status" className="text-sub font-medium text-ok">
              Salvo.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <Button size="md" onClick={() => void save()} disabled={!canSave} aria-busy={busy} className="rounded-full!">
            {busy ? "Salvando…" : confirming ? "Confirmar a troca" : "Salvar"}
          </Button>
          {confirming && (
            <Button variant="secondary" size="md" onClick={() => setConfirming(false)} className="rounded-full!">
              Cancelar
            </Button>
          )}
        </div>
      </div>
    </Card>
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
          <p className="text-foot text-ink-2">
            Se você trocar o endereço depois de imprimir, os cartazes e QR Codes antigos continuam funcionando: o endereço antigo leva para o novo. Baixe o cartaz de novo para passar a usar o novo.
          </p>
          <div aria-live="polite">
            {problem && (
              <p role="alert" className="text-sub font-medium text-bad">
                {problem}
              </p>
            )}
          </div>
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
    const result = await api.schoolSettings.update(schoolId, {
      suggestedAmountsCents: filled,
      allowCustomAmount: custom,
      freeAmountText: text.trim() || null,
    });
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
    <Card
      title="Valores da contribuição"
      action={
        <Button variant="secondary" size="md" onClick={start} className="rounded-full!">
          Editar
        </Button>
      }
    >
      <dl className="space-y-3 text-sub">
        <div>
          <dt className="text-ink-2">Valores sugeridos</dt>
          <dd className="font-semibold text-brand-800">{settings.suggestedAmountsCents.map(formatBRL).join(" · ")}</dd>
        </div>
        <div>
          <dt className="text-ink-2">Outro valor</dt>
          <dd>
            {settings.allowCustomAmount
              ? `A família pode digitar outro valor (de ${formatBRL(settings.minContributionCents)} a ${formatBRL(settings.maxContributionCents)}).`
              : "Só os valores sugeridos."}
          </dd>
        </div>
        <div>
          <dt className="text-ink-2">Texto ao lado do valor livre</dt>
          <dd className="[overflow-wrap:anywhere]">{settings.freeAmountText ?? "Nenhum."}</dd>
        </div>
      </dl>
      <FormModal open={open} title="Valores da contribuição" intro="Os valores que a família vê na página da escola." onClose={() => setOpen(false)} busy={busy}>
        <form
          method="post"
          noValidate
          aria-label="Valores da contribuição"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
          className="space-y-5"
        >
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
            {errors.suggested_amounts_cents && (
              <p role="alert" className="text-sub font-medium text-bad">
                {errors.suggested_amounts_cents}
              </p>
            )}
          </fieldset>
          <CheckboxField label="A família pode digitar outro valor" hint="Se desligar, só os valores sugeridos são aceitos." checked={custom} onChange={(e) => setCustom(e.target.checked)} />
          <TextAreaField
            label="Texto ao lado do valor livre"
            name="free-text"
            optional
            rows={2}
            maxLength={300}
            value={text}
            onChange={(e) => setText(e.target.value)}
            error={errors.free_amount_text}
          />
          <div aria-live="polite">
            {general && (
              <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
                {general}
              </p>
            )}
          </div>
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
    const result = await api.schoolSettings.update(schoolId, {
      monthlyGoalCents: goal === 0 ? null : goal,
      expectedContributions: count,
    });
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
    <Card
      title="Metas do mês"
      action={
        <Button variant="secondary" size="md" onClick={start} className="rounded-full!">
          Editar
        </Button>
      }
    >
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
        <form
          method="post"
          noValidate
          aria-label="Metas do mês"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
          className="space-y-5"
        >
          <TextField
            label="Meta de arrecadação do mês"
            optional
            name="goal"
            prefix="R$"
            inputMode="numeric"
            autoComplete="off"
            placeholder="Sem meta"
            value={goal === 0 ? "" : formatBRLNumber(goal)}
            onChange={(e) => setGoal(centsFromDigits(e.target.value))}
            error={errors.monthly_goal_cents}
          />
          <TextField
            label="Contribuições esperadas no mês"
            optional
            name="expected"
            inputMode="numeric"
            autoComplete="off"
            placeholder="Sem número"
            value={expected}
            onChange={(e) => setExpected(e.target.value.replace(/\D/g, "").slice(0, 6))}
            error={errors.expected_contributions}
          />
          <div aria-live="polite">
            {general && (
              <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
                {general}
              </p>
            )}
          </div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Salvar metas" pendingLabel="Salvando…" pending={busy} />
        </form>
      </FormModal>
    </Card>
  );
}
