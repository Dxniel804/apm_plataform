"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { Button, buttonClass } from "@/components/ui/Button";
import { InfoIcon, LockIcon } from "@/components/ui/icons";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import { describeAuthError } from "@/lib/auth-messages";

const MIN = 12;
const MAX = 128;

/**
 * A pagina do link do e-mail: escolher a senha nova. O token vem da URL e vai so no corpo do pedido; as senhas
 * so existem nos campos e no pedido (nao entram em estado, URL, log nem armazenamento) e sao limpas se falhar.
 * A API encerra todas as sessoes: depois e preciso entrar de novo.
 */
export function ResetPasswordForm({ token }: { token: string }) {
  const nextRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ next?: string; confirm?: string }>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const next = nextRef.current?.value ?? "";
    const confirm = confirmRef.current?.value ?? "";
    const length = [...next].length;
    const problems: { next?: string; confirm?: string } = {};
    if (length < MIN) problems.next = `Use pelo menos ${MIN} caracteres.`;
    else if (length > MAX) problems.next = `Use no máximo ${MAX} caracteres.`;
    else if (confirm !== next) problems.confirm = "As senhas não são iguais.";
    setErrors(problems);
    setError(null);
    if (problems.next) return nextRef.current?.focus();
    if (problems.confirm) return confirmRef.current?.focus();

    setPending(true);
    const result = await api.auth.confirmPasswordReset(token, next);
    setPending(false);
    if (result.ok) {
      if (nextRef.current) nextRef.current.value = "";
      if (confirmRef.current) confirmRef.current.value = "";
      return setDone(true);
    }
    if (nextRef.current) nextRef.current.value = "";
    if (confirmRef.current) confirmRef.current.value = "";
    setError(describeAuthError(result.error, "reset"));
  }

  if (done) {
    return (
      <div className="mt-8 space-y-5">
        <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-body font-medium text-ok">
          Senha alterada. Por segurança, todas as sessões abertas foram encerradas. Entre com a senha nova.
        </p>
        <Link href="/login" className={buttonClass("primary", "lg", "w-full")}>
          Ir para a entrada
        </Link>
      </div>
    );
  }
  return (
    <form method="post" noValidate onSubmit={onSubmit} aria-busy={pending} className="mt-8 space-y-5">
      <TextField
        variant="filled"
        label="Senha nova"
        name="new-password"
        type="password"
        autoComplete="new-password"
        hint={`De ${MIN} a ${MAX} caracteres.`}
        icon={<LockIcon size={18} />}
        inputRef={nextRef}
        error={errors.next}
      />
      <TextField
        variant="filled"
        label="Repita a senha nova"
        name="confirm-password"
        type="password"
        autoComplete="new-password"
        icon={<LockIcon size={18} />}
        inputRef={confirmRef}
        error={errors.confirm}
      />
      {error && (
        <p role="alert" className="flex items-start gap-2 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          <InfoIcon size={18} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Salvando…" : "Salvar a senha nova"}
      </Button>
    </form>
  );
}
