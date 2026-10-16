import type { Metadata } from "next";
import Link from "next/link";
import { LoginShell } from "@/components/auth/LoginShell";
import { buttonClass } from "@/components/ui/Button";
import { CashCoinIcon, InfoIcon } from "@/components/ui/icons";
import { LoginForm } from "@/components/login/LoginForm";
import { describeSsoError, forklinEnabled } from "@/lib/forklin";
import { safeNext } from "@/lib/safe-next";

export const metadata: Metadata = { title: "Entrar" };

type Props = {
  searchParams: Promise<{ next?: string | string[]; erro?: string | string[] }>;
};

export default async function LoginPage({ searchParams }: Props) {
  const { next, erro } = await searchParams;
  const sso = forklinEnabled();
  const problem = sso ? describeSsoError(erro) : null;
  return (
    <LoginShell
      title="Acessar sua conta"
      eyebrow="Bem-vindo à APM Digital"
      aside={
        <>
          {sso && (
            <>
              {/* <a>, nao <Link>: e um redirecionamento do servidor, e o prefetch do Link o chamaria sem clique. */}
              <a
                href="/sso/start"
                className={buttonClass("secondary", "lg", "w-full")}
              >
                Entrar com Forklin
              </a>
              {/* Texto fixo, igual para todo mundo: nao diz se um e-mail existe. A senha da Forklin vale so na Forklin. */}
              <p className="mt-2 text-center text-foot text-ink-2">
                O acesso ao APM Digital vem da sua conta Forklin: entre pelo
                botão acima.
              </p>
            </>
          )}
          {!sso && (
            <p className="text-center text-foot text-ink-2">
              Recebeu um convite?{" "}
              <span className="font-semibold text-ink">
                Abra o link que veio no seu e-mail para criar a sua conta.
              </span>
            </p>
          )}
          <div
            className="my-4 flex items-center gap-3"
            role="separator"
            aria-label="Para famílias"
          >
            <span className="h-px flex-1 bg-line" />
            <span className="text-[0.75rem] text-ink-3">
              é responsável por um aluno?
            </span>
            <span className="h-px flex-1 bg-line" />
          </div>
          <Link
            href="/escola"
            className={buttonClass(
              "secondary",
              "lg",
              "w-full border-pill-line bg-pill",
            )}
          >
            <CashCoinIcon size={18} />
            Contribuir com a APM, sem login
          </Link>
          <p className="mt-2 text-center text-foot text-ink-2">
            Famílias não precisam de login para contribuir.
          </p>
        </>
      }
    >
      {problem && (
        <p
          role="alert"
          className="mt-6 flex items-start gap-2 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad"
        >
          <InfoIcon size={18} className="mt-0.5 shrink-0" />
          <span>
            <span className="block font-semibold">{problem.title}</span>
            {problem.message}
          </span>
        </p>
      )}
      {!sso && <LoginForm next={safeNext(next)} />}
    </LoginShell>
  );
}
