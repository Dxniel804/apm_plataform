import type { Metadata } from "next";
import Link from "next/link";
import { AuthShell } from "@/components/auth/AuthShell";
import { ForgotPasswordForm } from "@/components/senha/ForgotPasswordForm";

export const metadata: Metadata = { title: "Esqueci minha senha" };

export default function ForgotPasswordPage() {
  return (
    <AuthShell title="Esqueci minha senha">
      <p className="mt-3 text-center text-body text-ink-2">
        Digite o e-mail da sua conta. Vamos enviar um link para você escolher uma senha nova.
      </p>
      <ForgotPasswordForm />
      <p className="mt-6 text-center text-foot text-ink-2">
        <Link href="/login" className="font-semibold text-brand-800 underline underline-offset-2">
          Voltar para a entrada
        </Link>
      </p>
    </AuthShell>
  );
}
