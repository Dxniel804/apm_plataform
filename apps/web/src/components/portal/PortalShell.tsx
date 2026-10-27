import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeftIcon } from "@/components/ui/icons";
import { Wordmark } from "@/components/ui/Logo";
import type { PublicSchool } from "@/lib/api/types";
import { SandboxGate } from "./SandboxGate";
import { SchoolMonogram } from "./SchoolMonogram";

/**
 * Moldura do portal publico (visual Paper v2): fundo nevoa, seta de voltar num botao redondo e o logo no
 * centro. O conteudo de cada tela entra numa `PortalSheet` (folha branca de cantos arredondados).
 * A cor e a da marca; a escola aparece pelo nome.
 */
export function PortalShell({ school, children }: { school: PublicSchool; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="mx-auto grid w-full max-w-5xl grid-cols-[2.75rem_1fr_2.75rem] items-center px-4 pt-3 sm:px-8 sm:pt-6">
        <Link
          href="/"
          aria-label="Voltar ao início"
          className="inline-flex size-11 items-center justify-center rounded-full border border-line-strong bg-white text-ink hover:bg-info-soft"
        >
          <ArrowLeftIcon size={22} />
        </Link>
        <div className="flex justify-center">
          <Wordmark width={96} />
        </div>
        <span aria-hidden="true" />
      </header>
      <main id="conteudo" tabIndex={-1} className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 pt-3 outline-none sm:px-8 sm:pb-8">
        <SandboxGate active={school.environment === "sandbox"}>{children}</SandboxGate>
      </main>
    </div>
  );
}

/** Topo da tela: monograma da escola, uma legenda curta e o titulo (o h1 da pagina e este bloco). */
export function PortalSchoolRow({ title, caption, monogram }: { title: string; caption: string; monogram: string }) {
  return (
    <div className="mb-4 flex items-center gap-3 px-1">
      <SchoolMonogram name={monogram} size={46} />
      <h1 className="min-w-0">
        <span className="block text-foot text-ink-2">{caption}</span>
        <span className="block text-[1.25rem] font-bold leading-tight tracking-[-0.01em] text-brand-800 [overflow-wrap:anywhere]">{title}</span>
      </h1>
    </div>
  );
}

/** Folha branca que sobe a partir do fundo. No celular vai de borda a borda e ate o pe da tela. */
export function PortalSheet({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`-mx-4 flex flex-1 flex-col rounded-t-[var(--r-xl)] bg-white px-5 pt-6 sm:mx-0 sm:rounded-[var(--r-xl)] sm:border sm:border-line sm:p-8 lg:p-10 ${className}`.trim()}
    >
      {children}
    </section>
  );
}
