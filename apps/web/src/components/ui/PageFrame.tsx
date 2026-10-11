import Link from "next/link";
import type { ReactNode } from "react";
import { Wordmark } from "./Logo";

const widths = {
  /** Formulario ou aviso curto. */
  narrow: "max-w-md px-5",
  /** Aviso com mais texto. */
  medium: "max-w-xl px-5",
  /** Erro e 404: alinhados a esquerda, na grade do site. */
  wide: "max-w-6xl px-5 sm:px-8",
} as const;

interface PageFrameProps {
  children: ReactNode;
  size?: keyof typeof widths;
  /**
   * Para onde o logo leva. `null` deixa o logo sem link (telas de erro: o roteador pode estar num
   * estado ruim, e quem quiser recomecar usa o botao da propria tela).
   */
  logoHref?: string | null;
}

/** Pagina simples da marca: logo no topo, conteudo no meio e o halftone no rodape. */
export function PageFrame({ children, size = "narrow", logoHref = "/" }: PageFrameProps) {
  return (
    <div className="halftone flex min-h-dvh flex-col">
      <header className="mx-auto w-full max-w-6xl px-5 pt-5 sm:px-8 sm:pt-7">
        {logoHref ? (
          <Link href={logoHref} className="inline-flex min-h-11 items-center rounded-lg">
            <Wordmark />
          </Link>
        ) : (
          <Wordmark />
        )}
      </header>
      <main
        id="conteudo"
        tabIndex={-1}
        className={`mx-auto flex w-full flex-1 flex-col justify-center pb-24 pt-8 outline-none ${widths[size]}`}
      >
        {children}
      </main>
    </div>
  );
}
