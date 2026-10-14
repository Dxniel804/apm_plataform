"use client";

import { notFound } from "next/navigation";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Button, ButtonLink } from "@/components/ui/Button";
import { CheckIcon, CopyIcon, LockIcon } from "@/components/ui/icons";
import { api } from "@/lib/api";
import type { Receipt } from "@/lib/api/types";
import { formatWait } from "@/lib/auth-messages";
import { PortalSheet } from "./PortalShell";
import { PaidStamp, ReceiptCard } from "./ReceiptCard";

type ViewState =
  | { kind: "checking" }
  | { kind: "receipt"; receipt: Receipt }
  | { kind: "unconfirmed" }
  | { kind: "not-found" }
  | { kind: "error"; message: string };

/**
 * Comprovante. O servidor entrega a pagina ja com o que a API respondeu (200 pago, 409 ainda nao, 404
 * vira a 404 do site); sem resposta definitiva, o HTML e NEUTRO ("Conferindo seu comprovante") e o
 * navegador consulta. Nunca se afirma "Pago" sem o 200 da API. O token so existe na URL desta pagina e
 * na memoria dela: nada em storage.
 */
export function ReceiptView({
  slug,
  token,
  initial,
}: {
  slug: string;
  token: string;
  initial: { receipt: Receipt } | { unconfirmed: true } | null;
}) {
  const [view, setView] = useState<ViewState>(
    initial === null
      ? { kind: "checking" }
      : "receipt" in initial
        ? { kind: "receipt", receipt: initial.receipt }
        : { kind: "unconfirmed" },
  );
  const [attempt, setAttempt] = useState(0);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useLayoutEffect(() => {
    // O servidor ja trouxe a resposta definitiva da API (200 ou 409): so consulta de novo se a pessoa pedir.
    if (attempt === 0 && initial !== null) return;
    let cancelled = false;
    void api.public.receipt(slug, token).then((result) => {
      if (cancelled) return;
      if (result.ok) setView({ kind: "receipt", receipt: result.data });
      else if (result.error.status === 404) setView({ kind: "not-found" });
      else if (result.error.status === 409) setView({ kind: "unconfirmed" });
      else if (result.error.code === "rate_limited") {
        setView({ kind: "error", message: `Muitas consultas seguidas. Aguarde ${formatWait(result.error.retryAfterSeconds)} e tente de novo.` });
      } else setView({ kind: "error", message: "Houve uma falha ao buscar o comprovante. Tente de novo em instantes." });
    });
    return () => {
      cancelled = true;
      clearTimeout(timer.current);
    };
    // `initial` so vale na primeira consulta.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, token, attempt]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 4000);
    } catch {
      setCopied(false);
    }
  }

  const sheet = (node: ReactNode) => <PortalSheet>{node}</PortalSheet>;

  // A mesma 404 estilizada para "nunca existiu" e "ainda nao existe" (sem enumeracao, ADR-010).
  if (view.kind === "not-found") notFound();

  if (view.kind === "checking") {
    return sheet(
      <div role="status" aria-live="polite" aria-busy="true" className="max-w-xl">
        <h1 className="text-title">Conferindo seu comprovante</h1>
        <p className="mt-3 text-body text-ink-2">Estamos conferindo este link. Isso leva só um instante.</p>
        <div aria-hidden="true" className="mt-8 w-full max-w-[26rem] rounded-[var(--r-lg)] border border-line bg-white p-6">
          <div className="skeleton h-4 w-40" />
          <div className="skeleton mt-6 h-10 w-48" />
          <div className="skeleton mt-8 h-4 w-full" />
          <div className="skeleton mt-3 h-4 w-5/6" />
          <div className="skeleton mt-3 h-4 w-2/3" />
        </div>
      </div>
    );
  }

  if (view.kind === "error") {
    return sheet(
      <div className="max-w-xl">
        <h1 className="text-title">Não conseguimos conferir agora</h1>
        <p role="alert" className="mt-3 text-body text-ink-2">{view.message}</p>
        <Button variant="solid" className="mt-7 w-full sm:w-auto" onClick={() => { setView({ kind: "checking" }); setAttempt((n) => n + 1); }}>
          Tentar de novo
        </Button>
      </div>
    );
  }

  if (view.kind === "unconfirmed") {
    return sheet(
      <div className="max-w-xl">
        <h1 className="text-title">Este pagamento ainda não foi confirmado</h1>
        <p className="mt-3 text-body text-ink-2">
          O comprovante só existe depois que o banco confirma o Pix. Se você acabou de pagar, aguarde um instante e
          atualize esta página. Se o pagamento estiver em análise pela escola, ele aparece aqui quando for confirmado.
        </p>
        <div className="mt-7 flex flex-col gap-3 sm:flex-row">
          <Button variant="solid" onClick={() => { setView({ kind: "checking" }); setAttempt((n) => n + 1); }}>Atualizar</Button>
          <ButtonLink href={`/escola/${slug}`} variant="secondary">
            Voltar para a escola
          </ButtonLink>
        </div>
      </div>
    );
  }

  const confirmed = view.receipt.status === "PAID";
  return (
    <div className="mx-auto flex w-full max-w-[28rem] flex-1 flex-col gap-5 pb-6 pt-2">
      <div className="flex flex-col items-center gap-1.5 text-center">
        {confirmed && (
          <div className="mb-2">
            <PaidStamp animate size={84} />
          </div>
        )}
        <h1 className="text-[1.625rem] font-bold leading-tight tracking-[-0.015em] text-brand-800">
          {confirmed ? "Contribuição confirmada" : "Comprovante da contribuição"}
        </h1>
        <p className="text-sub text-ink-2">
          {confirmed
            ? "Obrigado por apoiar a escola. Este é o seu comprovante: guarde o link, porque é ele que dá acesso a esta página."
            : "Acompanhe a situação do pagamento por este link."}
        </p>
      </div>

      <ReceiptCard receipt={view.receipt} />

      <p className="flex items-start gap-3 rounded-[var(--r-md)] bg-info-soft p-3.5 text-foot leading-snug text-ink">
        <LockIcon size={20} className="mt-px shrink-0 text-brand-800" />
        Não pedimos login. Quem tem o link vê este comprovante, então compartilhe com cuidado.
      </p>

      <div className="mt-auto flex flex-col gap-1">
        <Button variant="solid" onClick={copyLink} aria-describedby="receipt-copy-status" aria-label={copied ? undefined : "Copiar link do comprovante"}>
          {copied ? <CheckIcon size={20} className="pop" /> : <CopyIcon size={20} />}
          {copied ? "Link copiado" : "Copiar link"}
        </Button>
        <p id="receipt-copy-status" role="status" className="min-h-5 text-center text-foot text-ink-2">
          {copied && "Link copiado para a área de transferência."}
        </p>
        <ButtonLink href={`/escola/${slug}`} variant="plain">
          Fazer outra contribuição
        </ButtonLink>
      </div>
    </div>
  );
}
