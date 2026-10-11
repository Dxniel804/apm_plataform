import type { Metadata } from "next";
import { AuthShell } from "@/components/auth/AuthShell";
import { AcceptInvitationForm } from "@/components/invitation/AcceptInvitationForm";
import { ButtonLink } from "@/components/ui/Button";
import { getServerSession } from "@/lib/api/server";
import { plausibleInviteToken } from "@/lib/safe-next";

export const metadata: Metadata = { title: "Aceitar convite" };

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function AcceptInvitationPage({ searchParams }: Props) {
  const token = plausibleInviteToken((await searchParams).token);
  const auth = token ? await getServerSession() : null;
  const signedInAs =
    auth?.state === "authenticated" ? { fullName: auth.session.user.fullName, email: auth.session.user.email } : null;

  return (
    <AuthShell title="Aceitar convite">
      {token ? (
        <>
          <p className="mt-3 text-center text-body text-ink-2">
            Você foi convidado para atuar na tesouraria de uma APM. Confirme abaixo para aceitar.
          </p>
          <AcceptInvitationForm token={token} signedInAs={signedInAs} />
        </>
      ) : (
        <>
          <p role="alert" className="mt-3 text-center text-body text-ink-2">
            Este link de convite está incompleto ou inválido. Abra de novo o link que veio no seu e-mail ou peça um novo
            convite a quem convidou você.
          </p>
          <ButtonLink href="/login" variant="secondary" className="mt-6 w-full">
            Ir para a entrada
          </ButtonLink>
        </>
      )}
    </AuthShell>
  );
}
