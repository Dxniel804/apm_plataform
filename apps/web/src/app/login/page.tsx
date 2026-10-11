import type { Metadata } from "next";
import { AuthShell } from "@/components/auth/AuthShell";
import { LoginForm } from "@/components/login/LoginForm";
import { safeNext } from "@/lib/safe-next";

export const metadata: Metadata = { title: "Entrar" };

type Props = { searchParams: Promise<{ next?: string | string[] }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next } = await searchParams;
  return (
    <AuthShell title="Acessar sua conta">
      <LoginForm next={safeNext(next)} />

      <p className="mt-8 text-center text-sub text-ink-2">
        Acesso para quem cuida das contas da APM. Famílias não precisam de login para contribuir.
      </p>
      <p className="mt-2 text-center text-sub text-ink-2">
        Recebeu um convite? Abra o link que veio no seu e-mail para criar a sua conta.
      </p>
    </AuthShell>
  );
}
