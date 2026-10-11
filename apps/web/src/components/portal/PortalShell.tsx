import Link from "next/link";
import { ArrowLeftIcon } from "@/components/ui/icons";
import { Wordmark } from "@/components/ui/Logo";
import type { PublicSchool } from "@/lib/api/types";

/**
 * Moldura do portal publico (Figma "Responsaveis"): seta de voltar, logo no centro e o halftone no rodape.
 * A cor e a da marca; a escola aparece pelo nome (a API ainda manda `accentColor`, que nao e mais usada aqui).
 */
export function PortalShell({ children }: { school: PublicSchool; children: React.ReactNode }) {
  return (
    <div className="halftone min-h-dvh">
      <header className="mx-auto grid w-full max-w-5xl grid-cols-[2.75rem_1fr_2.75rem] items-center px-4 pt-4 sm:px-8 sm:pt-6">
        <Link
          href="/"
          aria-label="Voltar ao início"
          className="inline-flex size-11 items-center justify-center rounded-full text-ink-2 hover:bg-info-soft"
        >
          <ArrowLeftIcon size={26} />
        </Link>
        <div className="flex justify-center">
          <Wordmark width={112} />
        </div>
        <span aria-hidden="true" />
      </header>
      <main id="conteudo" tabIndex={-1} className="mx-auto w-full max-w-5xl px-5 pb-28 pt-6 outline-none sm:px-8 sm:pt-8">
        {children}
      </main>
    </div>
  );
}
