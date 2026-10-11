"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { InfoIcon } from "@/components/ui/icons";
import { TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import { describeAuthError } from "@/lib/auth-messages";

/**
 * Login REAL (POST /api/v1/auth/login, mesma origem). A sessao e um cookie HttpOnly que a API
 * grava: o site nunca ve nem guarda token. A senha so existe no campo e no corpo do pedido: nao
 * entra em estado do React, URL, log nem armazenamento, e o campo e limpo quando o login falha.
 * Os erros vem do `code` da API, em portugues, sem dizer se o e-mail existe.
 */
export function LoginForm({ next = "/painel" }: { next?: string }) {
  const router = useRouter();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [blockedForMs, setBlockedForMs] = useState<number | null>(null);

  // Bloqueio por tentativas (429): o botao volta sozinho quando o tempo da API passa.
  useEffect(() => {
    if (blockedForMs === null) return;
    const id = setTimeout(() => setBlockedForMs(null), blockedForMs);
    return () => clearTimeout(id);
  }, [blockedForMs]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || blockedForMs !== null) return;
    const email = emailRef.current?.value.trim() ?? "";
    const password = passwordRef.current?.value ?? "";

    const missing: { email?: string; password?: string } = {};
    if (!email) missing.email = "Informe o seu e-mail.";
    if (!password) missing.password = "Informe a sua senha.";
    setFieldErrors(missing);
    setError(null);
    if (missing.email) return emailRef.current?.focus();
    if (missing.password) return passwordRef.current?.focus();

    setPending(true);
    const result = await api.auth.login(email, password);
    if (result.ok) {
      router.replace(next); // fica "pending": a pagina troca em seguida
      return;
    }
    setPending(false);
    if (passwordRef.current) passwordRef.current.value = "";
    setError(describeAuthError(result.error, "login"));
    if (result.error.code === "rate_limited") {
      setBlockedForMs((result.error.retryAfterSeconds ?? 60) * 1000);
    } else {
      passwordRef.current?.focus();
    }
  }

  return (
    <form method="post" noValidate onSubmit={onSubmit} aria-busy={pending} className="mt-8 space-y-6">
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
        inputRef={emailRef}
        error={fieldErrors.email}
      />
      <div>
        <TextField
          variant="filled"
          label="Sua senha"
          name="password"
          type={showPassword ? "text" : "password"}
          autoComplete="current-password"
          placeholder="Digite a sua senha"
          inputRef={passwordRef}
          error={fieldErrors.password}
        />
        {/* No Figma, "Esqueceu sua senha?" fica neste lugar. Ainda nao existe recuperacao de senha na API
            (docs/auth.md), entao o espaco serve ao botao de mostrar/ocultar. */}
        <div className="mt-1 flex justify-end">
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-pressed={showPassword}
            className="inline-flex min-h-11 items-center rounded-full px-1 text-sub font-semibold text-brand-800 hover:underline"
          >
            {showPassword ? "Ocultar a senha" : "Mostrar a senha"}
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className="flex items-start gap-2 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          <InfoIcon size={18} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending || blockedForMs !== null} className="w-full">
        {pending ? "Entrando…" : "Entrar"}
      </Button>
    </form>
  );
}
