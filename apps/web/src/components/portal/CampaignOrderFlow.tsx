"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { CreatedContribution, OrderLine, PublicCampaign, PublicSchool } from "@/lib/api/types";
import { formatBRL } from "@/lib/money";
import { describeOrderError } from "@/lib/public-messages";
import {
  validateIdentification,
  visibleFields,
  type IdentificationErrors,
  type IdentificationField,
  type IdentificationValues,
} from "@/lib/validation";
import { CampaignCartStep } from "./CampaignCartStep";
import { StepProgress, SummaryCard, type Step } from "./FlowChrome";
import { PortalSchoolRow, PortalSheet } from "./PortalShell";
import { IdentificationStep } from "./IdentificationStep";
import { PixPayment } from "./PixPayment";
import { ReviewStep } from "./ReviewStep";

const STEP_NAMES: Partial<Record<Step, string>> = { amount: "Produtos" };

/**
 * O pedido de uma campanha (sem login, ADR-010): escolher os produtos, dizer quem esta pagando, conferir e pagar
 * pelo Pix. O mesmo caminho da contribuicao livre, com o carrinho no lugar do valor. A tela manda QUAIS produtos
 * e QUANTOS; o servidor le os precos, soma e cria o Pix. O total que a tela mostra e so uma conta de tela.
 */
export function CampaignOrderFlow({ school: publicSchool, campaign }: { school: PublicSchool; campaign: PublicCampaign }) {
  // Uma campanha que entrega pede o aluno e a turma, qualquer que seja o que a escola pede na contribuicao do mes
  // (a API exige os dois do mesmo jeito).
  const school: PublicSchool = campaign.askStudentClass
    ? { ...publicSchool, identification: { ...publicSchool.identification, studentName: "REQUIRED", classroom: "REQUIRED" } }
    : publicSchool;
  const fields = visibleFields(school.identification);
  // "amount" e a etapa do carrinho (a etapa dos produtos); o resto e igual ao da contribuicao.
  const steps: Step[] = fields.length > 0 ? ["amount", "identification", "review", "pix"] : ["amount", "review", "pix"];

  const [step, setStepState] = useState<Step>("amount");
  const [navigated, setNavigated] = useState(false);
  const setStep = (next: Step) => {
    setNavigated(true);
    setStepState(next);
  };
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [cartError, setCartError] = useState<string | null>(null);
  const [lineErrors, setLineErrors] = useState<Record<string, string>>({});
  const [values, setValues] = useState<IdentificationValues>({});
  const [errors, setErrors] = useState<IdentificationErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // O token (segredo da familia) so vive aqui, em memoria: nunca em storage nem em URL ate o comprovante.
  const [created, setCreated] = useState<CreatedContribution | null>(null);
  const [priceNotice, setPriceNotice] = useState<string | null>(null);
  // A Idempotency-Key e uma por TENTATIVA (mesmo carrinho e mesmos dados): reaproveitada se o POST for
  // repetido por falha de rede e trocada quando a pessoa muda algo.
  const attempt = useRef<{ key: string; signature: string } | null>(null);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    headingRef.current?.focus();
  }, [step]);

  // O que esta no carrinho, na ordem dos produtos (so uma conta de tela).
  const cart = campaign.items.filter((item) => (quantities[item.id] ?? 0) > 0).map((item) => ({ item, quantity: quantities[item.id] ?? 0 }));
  const totalCents = cart.reduce((sum, line) => sum + line.item.priceCents * line.quantity, 0);
  const lines = cart.map((line) => ({ name: line.item.name, quantity: line.quantity, unitPriceCents: line.item.priceCents }));
  const description = `${campaign.title} · ${cart.reduce((sum, line) => sum + line.quantity, 0)} ${cart.reduce((sum, line) => sum + line.quantity, 0) === 1 ? "item" : "itens"}`;

  function onQuantity(itemId: string, quantity: number) {
    setQuantities((prev) => ({ ...prev, [itemId]: quantity }));
    setCartError(null);
    setLineErrors((prev) => (prev[itemId] ? { ...prev, [itemId]: "" } : prev));
  }

  function continueFromCart() {
    if (cart.length === 0) {
      setCartError("Escolha pelo menos um produto.");
      return;
    }
    setCartError(null);
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

  async function createOrder() {
    if (cart.length === 0) return;
    const orderLines: OrderLine[] = cart.map((line) => ({ itemId: line.item.id, quantity: line.quantity }));
    const input = { lines: orderLines, identification: values };
    const signature = JSON.stringify(input);
    if (attempt.current?.signature !== signature) attempt.current = { key: crypto.randomUUID(), signature };
    setSubmitting(true);
    setSubmitError(null);
    const result = await api.public.createOrder(school.slug, campaign.id, input, attempt.current.key);
    setSubmitting(false);
    if (!result.ok) {
      const problems = describeOrderError(result.error);
      if (result.error.code === "idempotency_key_reused") attempt.current = null;
      const refused = Object.keys(problems.lines);
      if (refused.length > 0) {
        const byItem: Record<string, string> = {};
        for (const index of refused) {
          const line = orderLines[Number(index)];
          if (line) byItem[line.itemId] = problems.lines[Number(index)]!;
        }
        setLineErrors(byItem);
        setCartError("Alguns produtos não estão mais como você escolheu. Confira os avisos abaixo.");
        setStep("amount");
        return;
      }
      const fieldProblems = Object.keys(problems.fields).filter((f) => fields.includes(f as IdentificationField));
      if (fieldProblems.length > 0) {
        setErrors(problems.fields);
        setStep("identification");
        return;
      }
      setSubmitError(problems.general ?? "Não foi possível gerar o Pix agora. Tente de novo em instantes. Nada foi cobrado.");
      return;
    }
    attempt.current = null; // pedido criado: a chave nao serve mais para nada
    // Os precos podem ter mudado entre abrir a pagina e pagar: quem vale e o valor da API, e a tela diz.
    setPriceNotice(
      result.data.amountCents !== totalCents
        ? `Os preços mudaram desde que você abriu a página. O valor deste Pix é ${formatBRL(result.data.amountCents)}.`
        : null,
    );
    setCreated(result.data);
    setStep("pix");
  }

  function restart() {
    setStep("amount");
    setQuantities({});
    setValues({});
    setErrors({});
    setCartError(null);
    setLineErrors({});
    setSubmitError(null);
    setPriceNotice(null);
    setCreated(null);
    attempt.current = null;
  }

  return (
    <>
      <PortalSchoolRow
        title={campaign.title}
        caption={school.apmName.includes(school.name) ? school.apmName : `${school.name} · ${school.apmName}`}
        monogram={school.name}
      />
      <PortalSheet>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-start lg:gap-14">
        <div className="min-w-0">
          <StepProgress steps={steps} current={step} labels={STEP_NAMES} />

          <div key={step} className={navigated ? "step-in" : undefined}>
            {step === "amount" && (
              <CampaignCartStep
                slug={school.slug}
                campaign={campaign}
                quantities={quantities}
                error={cartError}
                lineErrors={lineErrors}
                headingRef={headingRef}
                onChange={onQuantity}
                onContinue={continueFromCart}
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

            {step === "review" && cart.length > 0 && (
              <ReviewStep
                schoolName={school.name}
                description={description}
                amountCents={totalCents}
                lines={lines}
                editLabel="Alterar os produtos"
                identification={values}
                submitting={submitting}
                error={submitError}
                headingRef={headingRef}
                onEditAmount={() => setStep("amount")}
                onEditIdentification={fields.length > 0 ? () => setStep("identification") : null}
                onBack={() => setStep(fields.length > 0 ? "identification" : "amount")}
                onSubmit={createOrder}
              />
            )}

            {step === "pix" && created && (
              <>
                {priceNotice && (
                  <p role="status" className="mb-5 rounded-[var(--r-md)] bg-warn-soft px-4 py-3 text-sub font-medium text-warn">
                    {priceNotice}
                  </p>
                )}
                <PixPayment key={created.token} slug={school.slug} token={created.token} initial={created} onRestart={restart} />
              </>
            )}
          </div>
        </div>

        <div className="hidden lg:sticky lg:top-24 lg:block">
          <SummaryCard
            heading="Seu pedido para"
            label="Resumo do pedido"
            schoolName={school.name}
            amountCents={cart.length === 0 ? null : step === "pix" && created ? created.amountCents : totalCents}
            description={cart.length === 0 ? null : campaign.title}
            lines={lines.map((line) => ({ name: line.name, quantity: line.quantity, totalCents: line.unitPriceCents * line.quantity }))}
            identification={step === "amount" ? {} : values}
          >
            <p className="mt-5 border-t border-line pt-4 text-foot text-ink-2">
              Sem login. O comprovante chega por um link só seu, e a escola só vê os dados que você informar.
            </p>
          </SummaryCard>
        </div>
      </div>
      </PortalSheet>
    </>
  );
}
