import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { Wordmark } from "@/components/ui/Logo";

/**
 * Moldura das telas de acesso (login e convite), do Figma "Tela Login": de um lado a arte azul da marca
 * com o logo branco, do outro o formulario sobre o halftone. No celular a arte vira um banner no topo.
 */
export function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid min-h-dvh gap-3 p-3 lg:grid-cols-2">
      <header className="relative min-h-36 overflow-hidden rounded-[1.75rem] bg-brand-800 sm:min-h-44 lg:min-h-0 lg:rounded-[2.5rem]">
        <Image
          src="/brand/login-art.webp"
          alt=""
          fill
          priority
          sizes="(min-width: 1024px) 50vw, 100vw"
          className="object-cover object-[center_62%]"
        />
        <Link href="/" className="absolute left-5 top-3 inline-flex min-h-11 items-center lg:left-9 lg:top-7">
          <Wordmark tone="white" width={112} priority />
        </Link>
      </header>

      <div className="halftone flex flex-col justify-center rounded-[1.75rem] px-2 py-10 sm:px-8 lg:py-16">
        <main id="conteudo" tabIndex={-1} className="mx-auto w-full max-w-[28rem] outline-none">
          <h1 className="text-center text-[clamp(1.75rem,1.35rem+1.2vw,2.5rem)] font-semibold leading-tight tracking-[-0.015em] text-ink">
            {title}
          </h1>
          {children}
        </main>
      </div>
    </div>
  );
}
