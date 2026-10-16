import Link from "next/link";
import type { ReactNode } from "react";
import Aurora from "@/components/ui/Aurora";
import { Wordmark } from "@/components/ui/Logo";

/**
 * Moldura do login: tela cheia (sem rolagem) com o fundo de aurora sobre branco, a marca grande a esquerda
 * (so no computador) e o formulario num cartao de vidro fosco a direita, afastado da borda. Abaixo
 * do formulario ficam as outras entradas (`aside`: Forklin, convite, familias). No celular: marca no
 * topo e o cartao centralizado. O fundo e decorativo (alt vazio) e o cartao e opaco o bastante para
 * o texto manter o contraste sobre qualquer trecho da imagem.
 */
export function LoginShell({
  title,
  eyebrow,
  aside,
  children,
}: {
  title: string;
  eyebrow?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-x-hidden bg-white">
      <div aria-hidden="true" className="absolute inset-0 -z-10">
        <Aurora
          colorStops={["#346ae3", "#98c7ff", "#4b89f4"]}
          amplitude={1}
          blend={0.5}
          height={0.45}
          speed={1}
          glow={0.6}
          scale={1}
          brightness={1}
          layers={1}
          direction="top"
          opacity={1}
          mouseInteraction
          intro
          lightMode
        />
      </div>

      <header className="relative z-10 px-5 pt-3 sm:px-10 lg:absolute lg:left-0 lg:top-0 lg:px-16 lg:pt-8">
        <Link href="/" className="inline-flex min-h-11 items-center">
          <Wordmark width={104} priority />
        </Link>
      </header>

      <div className="flex flex-1 items-center justify-center px-5 pb-4 pt-1 sm:px-10 lg:justify-between lg:gap-12 lg:pl-16 lg:pr-[8vw] lg:py-6 xl:pl-[6vw] xl:pr-[18vw]">
        <div className="hidden min-w-0 max-w-[22rem] lg:block">
          <Link href="/" className="inline-block">
            <Wordmark width={340} priority />
          </Link>
          <p className="mt-6 text-[1.5rem] font-semibold leading-snug tracking-[-0.01em] text-brand-800">
            APM Digital
          </p>
          <p className="mt-2 max-w-[26rem] text-[1.0625rem] leading-relaxed text-ink-2">
            Pix com comprovante e prestação de contas da associação, no mesmo
            lugar, com as famílias vendo para onde vai cada real.
          </p>
        </div>

        <main
          id="conteudo"
          tabIndex={-1}
          className="w-full max-w-[28rem] shrink-0 rounded-[1.75rem] border border-white/80 bg-white/75 px-6 py-5 shadow-[0_24px_64px_-24px_rgba(44,81,224,0.35)] outline-none backdrop-blur-xl sm:px-9 sm:py-8 lg:max-w-[32rem] xl:max-w-[36rem] lg:px-10 xl:px-12 lg:py-9 [@media(max-height:700px)]:!py-3"
        >
          {eyebrow && (
            <p className="text-[1rem] text-ink-2 [@media(max-height:760px)]:hidden">
              {eyebrow}
            </p>
          )}
          <h1 className="text-[clamp(1.75rem,1.45rem+1vw,2.25rem)] font-bold leading-[1.1] tracking-[-0.02em] text-brand-800">
            {title}
          </h1>
          {children}
          {aside && (
            <div className="mt-5 border-t border-line pt-4 [@media(max-height:700px)]:mt-3 [@media(max-height:700px)]:pt-3">
              {aside}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
