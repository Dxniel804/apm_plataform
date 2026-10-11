import { Button } from "@/components/ui/Button";
import { PageFrame } from "@/components/ui/PageFrame";
import type { Session } from "@/lib/api/types";
import { MembershipList } from "./MembershipList";

interface ContextChooserProps {
  session: Session;
  busy: boolean;
  signingOut: boolean;
  problem: string | null;
  onSelect: (membershipId: string) => void;
  onSignOut: () => void;
}

/**
 * Sessao sem vinculo ativo (docs/auth.md, R3): quem tem varios vinculos escolhe onde atuar antes
 * de ver o painel, e quem nao tem nenhum ve um aviso. As rotas com papel respondem 409 ate la.
 */
export function ContextChooser({ session, busy, signingOut, problem, onSelect, onSignOut }: ContextChooserProps) {
  const none = session.memberships.length === 0;
  return (
    <PageFrame logoHref={null}>
      <h1 className="text-title sm:text-[2.25rem]">{none ? "Sem vínculo ativo" : "Onde você vai atuar?"}</h1>
      <p className="mt-2 text-body text-ink-2">
        {none
          ? `${session.user.fullName}, a sua conta ainda não tem vínculo ativo com nenhuma APM. Peça um convite a quem administra a sua escola.`
          : `${session.user.fullName}, a sua conta tem mais de um vínculo. Escolha com qual deles você quer entrar agora.`}
      </p>
      {!none && (
        <div className="mt-6 rounded-[var(--r-lg)] border border-line bg-surface p-2">
          <MembershipList memberships={session.memberships} activeId={null} disabled={busy} onSelect={onSelect} />
        </div>
      )}
      {problem && (
        <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {problem}
        </p>
      )}
      <Button variant="secondary" onClick={onSignOut} disabled={signingOut} className="mt-6 w-full">
        {signingOut ? "Saindo…" : "Sair"}
      </Button>
    </PageFrame>
  );
}
