"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { InfoIcon, MailIcon } from "@/components/ui/icons";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import { describeAuthError } from "@/lib/auth-messages";

/**
 * "Esqueci minha senha": so pede o e-mail. A resposta da API e a mesma para qualquer e-mail, e o texto
 * de sucesso tambem: nunca diz se existe uma conta (docs/adr-password-reset.md).
 */
export function ForgotPasswordForm() {
  const emailRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | undefined>();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const email = emailRef.current?.value.trim() ?? "";
    setError(null);
    if (!email) {
      setFieldError("Informe o seu e-mail.");
      return emailRef.current?.focus();
    }
    setFieldError(undefined);
    setPending(true);
    const result = await api.auth.requestPasswordReset(email);
    setPending(false);
    if (result.ok) return setSent(true);
    setError(describeAuthError(result.error, "reset"));
  }

  if (sent) {
    return (
      <p role="status" className="mt-8 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-body font-medium text-ok">
        Se este e-mail tem uma conta, enviamos um link para escolher uma senha nova. Ele vale por 30 minutos. Confira também a caixa de spam.
      </p>
    );
  }
  return (
    <form method="post" noValidate onSubmit={onSubmit} aria-busy={pending} className="mt-8 space-y-5">
      <TextField
        variant="filled"
        label="Seu e-mail"
        name="email"
        type="email"
        inputMode="email"
        autoComplete="username"
        spellCheck={false}
        autoCapitalize="none"
        autoCorrect="off"
        placeholder="voce@escola.com.br"
        icon={<MailIcon size={18} />}
        inputRef={emailRef}
        error={fieldError}
      />
      {error && (
        <p role="alert" className="flex items-start gap-2 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          <InfoIcon size={18} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Enviando…" : "Enviar o link"}
      </Button>
    </form>
  );
}
