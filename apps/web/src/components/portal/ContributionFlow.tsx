"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { CreatedContribution, PublicCampaignSummary, PublicSchool } from "@/lib/api/types";
import { formatMonthYear } from "@/lib/format";
import { describeContributionError } from "@/lib/public-messages";
import {
  validateAmount,
  validateIdentification,
  visibleFields,
  type IdentificationErrors,
  type IdentificationField,
  type IdentificationValues,
} from "@/lib/validation";
import { AmountStep, CUSTOM_CHOICE, suggestedCents } from "./AmountStep";
import { CampaignShelf } from "./CampaignShelf";
import { StepProgress, SummaryCard, type Step } from "./FlowChrome";
import { PortalSchoolRow, PortalSheet } from "./PortalShell";
import { BagIcon, CashCoinIcon } from "@/components/ui/icons";
import { IdentificationStep } from "./IdentificationStep";
import { PixPayment } from "./PixPayment";
import { ReviewStep } from "./ReviewStep";

/**
 * Fluxo publico de contribuicao (sem login, ADR-010). A validacao aqui e de UX; o backend
 * revalida tudo e e quem confirma o pagamento.
 */
export function ContributionFlow({ school, campaigns = [] }: { school: PublicSchool; campaigns?: PublicCampaignSummary[] }) {
  const fields = visibleFields(school.identification);
  const steps: Step[] = fields.length > 0 ? ["amount", "identification", "review", "pix"] : ["amount", "review", "pix"];

  const [view, setView] = useState<"mensal" | "campanhas">("mensal");
  const [step, setStepState] = useState<Step>("amount");
  // A entrada animada so acontece depois de uma acao do usuario (nunca no carregamento da pagina).
  const [navigated, setNavigated] = useState(false);
  const setStep = (next: Step) => {
    setNavigated(true);
    setStepState(next);
  };
  const [choice, setChoice] = useState<string | null>(null);
  const [customCents, setCustomCents] = useState(0);
  // O mes a que a contribuicao se refere: vem o mes atual (o ultimo que a API oferece).
  const currentMonth = school.referenceMonths.at(-1) ?? null;
  const [referenceMonth, setReferenceMonth] = useState<string | null>(currentMonth);
  const [amountError, setAmountError] = useState<string | null>(null);
  const [values, setValues] = useState<IdentificationValues>({});
  const [errors, setErrors] = useState<IdentificationErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // O token (segredo da familia) so vive aqui, em memoria: nunca em storage nem em URL ate o comprovante.
  const [created, setCreated] = useState<CreatedContribution | null>(null);
  // A Idempotency-Key e tao secreta quanto o token: uma por TENTATIVA (mesmo valor e mesmos dados),
  // reaproveitada se o POST for repetido por falha de rede e trocada quando o usuario muda algo.
  const attempt = useRef<{ key: string; signature: string } | null>(null);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(false);

  // Ao trocar de etapa, o foco vai para o titulo da etapa (teclado e leitores de tela).
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  const suggested = suggestedCents(choice);
  const amountCents = choice === CUSTOM_CHOICE ? customCents : suggested;
  const description =
    choice === CUSTOM_CHOICE ? (customCents > 0 ? "Valor livre" : null) : suggested !== null ? "Valor sugerido pela APM" : null;

  function onChoice(next: string) {
    setChoice(next);
    setAmountError(null);
  }

  function continueFromAmount() {
    if (choice === null) {
      setAmountError("Escolha uma cota ou informe outro valor.");
      return;
    }
    if (choice === CUSTOM_CHOICE) {
      const check = validateAmount(customCents, { minCents: school.minAmountCents, maxCents: school.maxAmountCents });
      if (!check.ok) {
        setAmountError(check.message);
        return;
      }
    }
    setAmountError(null);
    setStep(fields.length > 0 ? "identification" : "review");
  }

  function continueFromIdentification(focusField: (field: IdentificationField) => void) {
    const result = validateIdentification(values, school.identification);
    setErrors(result.errors);
    if (!result.ok) {
      const first = fields.find((f) => result.errors[f]);
      if (first) focusField(first);
      return;
    }
    setValues(result.cleaned);
    setStep("review");
  }

  async function createCharge() {
    if (amountCents === null || amountCents <= 0) return;
    const input = { amountCents, identification: values, referenceMonth };
    const signature = JSON.stringify(input);
    if (attempt.current?.signature !== signature) attempt.current = { key: crypto.randomUUID(), signature };
    setSubmitting(true);
    setSubmitError(null);
    const result = await api.public.createContribution(school.slug, input, attempt.current.key);
    setSubmitting(false);
    if (!result.ok) {
      const problems = describeContributionError(result.error);
      if (result.error.code === "idempotency_key_reused") attempt.current = null;
      const fieldProblems = Object.keys(problems.fields).filter((f) => fields.includes(f as IdentificationField));
      if (fieldProblems.length > 0) {
        setErrors(problems.fields);
        setStep("identification");
        return;
      }
      if (problems.amount || problems.referenceMonth) {
        setAmountError(problems.amount ?? problems.referenceMonth ?? null);
        setStep("amount");
        return;
      }
      setSubmitError(problems.general ?? "Não foi possível gerar o Pix agora. Tente de novo em instantes.");
      return;
    }
    attempt.current = null; // contribuicao criada: a chave nao serve mais para nada
    setCreated(result.data);
    setStep("pix");
  }

  function restart() {
    setStep("amount");
    setChoice(null);
    setCustomCents(0);
    setReferenceMonth(currentMonth);
    setValues({});
    setErrors({});
    setAmountError(null);
    setSubmitError(null);
    setCreated(null);
    attempt.current = null;
  }

  const schoolLabel = school.apmName.includes(school.name) ? school.apmName : `${school.name} · ${school.apmName}`;
  // O seletor "Contribuicao mensal | Campanhas" so aparece na primeira etapa e so se a escola tem campanhas a venda.
  const showTabs = step === "amount" && campaigns.length > 0;
  const onCampaigns = showTabs && view === "campanhas";
  const tabs = [
    { id: "mensal", label: "Contribuição mensal", icon: <CashCoinIcon size={16} /> },
    { id: "campanhas", label: "Campanhas", icon: <BagIcon size={16} /> },
  ] as const;

  return (
    <>
      <PortalSchoolRow title={schoolLabel} caption="Contribuir com a APM" monogram={school.name} />

      {showTabs && (
        <div role="tablist" aria-label="O que você quer fazer" className="mb-4 flex gap-1 rounded-2xl bg-chip p-1">
          {tabs.map((tab) => {
            const active = view === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={active}
                aria-controls="portal-panel"
                onClick={() => setView(tab.id)}
                className={`flex min-h-11 flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-xl border px-2 text-[0.875rem] transition-colors ${
                  active ? "border-pill-line bg-white font-semibold text-brand-800" : "border-transparent font-medium text-ink-2 hover:bg-white/60"
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            );
          })}
        </div>
      )}

      <PortalSheet>
      <div id="portal-panel" role={showTabs ? "tabpanel" : undefined} aria-labelledby={showTabs ? `tab-${view}` : undefined} className="flex flex-1 flex-col">
      {/* As duas visoes ficam no HTML (a inativa so escondida): a vitrine existe mesmo antes do JavaScript. */}
      <div hidden={!onCampaigns}>
        <CampaignShelf slug={school.slug} campaigns={campaigns} />
      </div>
      <div hidden={onCampaigns}>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-start lg:gap-14">
        <div className="min-w-0">
          <StepProgress steps={steps} current={step} />

          <div key={step} className={navigated ? "step-in" : undefined}>
            {step === "amount" && (
              <AmountStep
                school={school}
                choice={choice}
                customCents={customCents}
                error={amountError}
                headingRef={headingRef}
                onChoice={onChoice}
                onCustomChange={(cents) => {
                  setCustomCents(cents);
                  setAmountError(null);
                }}
                onContinue={continueFromAmount}
                referenceMonth={referenceMonth}
                onReferenceMonth={setReferenceMonth}
              />
            )}

            {step === "identification" && (
              <IdentificationStep
                school={school}
                values={values}
                errors={errors}
                headingRef={headingRef}
                onChange={(field, value) => {
                  setValues((prev) => ({ ...prev, [field]: value }));
                  setErrors((prev) => ({ ...prev, [field]: undefined }));
                }}
                onBack={() => setStep("amount")}
                onContinue={continueFromIdentification}
              />
            )}

            {step === "review" && amountCents !== null && description !== null && (
              <ReviewStep
                schoolName={school.name}
                description={description}
                amountCents={amountCents}
                identification={values}
                submitting={submitting}
                error={submitError}
                headingRef={headingRef}
                onEditAmount={() => setStep("amount")}
                onEditIdentification={fields.length > 0 ? () => setStep("identification") : null}
                onBack={() => setStep(fields.length > 0 ? "identification" : "amount")}
                onSubmit={createCharge}
                referenceMonthLabel={referenceMonth ? formatMonthYear(referenceMonth) : null}
              />
            )}

            {step === "pix" && created && (
              <PixPayment
                key={created.token}
                slug={school.slug}
                token={created.token}
                initial={created}
                onRestart={restart}
              />
            )}
          </div>
        </div>

        <div className="hidden lg:sticky lg:top-24 lg:block">
          <SummaryCard
            schoolName={school.name}
            amountCents={amountCents}
            description={description}
            identification={step === "amount" ? {} : values}
          >
            <p className="mt-5 border-t border-line pt-4 text-foot text-ink-2">
              Sem login. O comprovante chega por um link só seu, e a escola só vê os dados que você informar.
            </p>
          </SummaryCard>
        </div>
      </div>
      </div>
      </div>
      </PortalSheet>
    </>
  );
}
