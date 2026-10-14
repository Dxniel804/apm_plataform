import type { Metadata } from "next";
import Link from "next/link";
import { AuthShell } from "@/components/auth/AuthShell";
import { buttonClass } from "@/components/ui/Button";
import { CashCoinIcon } from "@/components/ui/icons";
import { LoginForm } from "@/components/login/LoginForm";
import { safeNext } from "@/lib/safe-next";

export const metadata: Metadata = { title: "Entrar" };

type Props = { searchParams: Promise<{ next?: string | string[] }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next } = await searchParams;
  return (
    <AuthShell title="Acessar sua conta" eyebrow="Bem-vindo à APM Digital">
      <LoginForm next={safeNext(next)} />

      <p className="mt-5 text-center text-foot text-ink-2">
        Recebeu um convite? <span className="font-semibold text-ink">Abra o link que veio no seu e-mail para criar a sua conta.</span>
      </p>

      <div className="mt-6 flex items-center gap-3" role="separator" aria-label="Para famílias">
        <span className="h-px flex-1 bg-line" />
        <span className="text-[0.75rem] text-ink-3">é responsável por um aluno?</span>
        <span className="h-px flex-1 bg-line" />
      </div>
      <Link href="/" className={buttonClass("secondary", "lg", "mt-4 w-full border-pill-line bg-pill")}>
        <CashCoinIcon size={18} />
        Contribuir com a APM, sem login
      </Link>
      <p className="mt-3 text-center text-foot text-ink-2">Acesso para quem cuida das contas da APM. Famílias não precisam de login para contribuir.</p>
    </AuthShell>
  );
}
