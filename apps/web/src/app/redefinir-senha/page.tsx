import type { Metadata } from "next";
import { AuthShell } from "@/components/auth/AuthShell";
import { ResetPasswordForm } from "@/components/senha/ResetPasswordForm";
import { ButtonLink } from "@/components/ui/Button";
import { plausibleInviteToken } from "@/lib/safe-next";

export const metadata: Metadata = { title: "Escolher senha nova" };

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function ResetPasswordPage({ searchParams }: Props) {
  const token = plausibleInviteToken((await searchParams).token);
  return (
    <AuthShell title="Escolher senha nova">
      {token ? (
        <ResetPasswordForm token={token} />
      ) : (
        <>
          <p role="alert" className="mt-3 text-center text-body text-ink-2">
            Este link está incompleto ou inválido. Abra de novo o link que veio no seu e-mail ou peça um novo.
          </p>
          <ButtonLink href="/esqueci-senha" variant="secondary" className="mt-6 w-full">
            Pedir um link novo
          </ButtonLink>
        </>
      )}
    </AuthShell>
  );
}
