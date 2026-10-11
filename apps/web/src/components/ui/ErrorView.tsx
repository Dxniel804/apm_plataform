"use client";

import { Button, buttonClass } from "@/components/ui/Button";
import { PageFrame } from "@/components/ui/PageFrame";

/**
 * Tela de erro inesperado (error.tsx e global-error.tsx). Texto em portugues, com a identidade do
 * produto. NUNCA mostra error.message (pode conter detalhe interno); so o codigo (digest), que e um
 * hash, para a tesouraria poder informar a quem cuida do sistema.
 */
export function ErrorView({ reset, digest }: { reset: () => void; digest?: string }) {
  return (
    <PageFrame size="wide" logoHref={null}>
      <h1 className="max-w-[20ch] text-balance text-title sm:text-[2.5rem]">Algo deu errado por aqui</h1>
      <p className="mt-3 max-w-[46ch] text-body text-ink-2">
        Não conseguimos mostrar esta página. Nada foi cobrado nem enviado. Tente de novo e, se continuar, volte ao início.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Button variant="solid" onClick={reset}>
          Tentar de novo
        </Button>
        {/* <a> e nao <Link>: um erro pode deixar o roteador num estado ruim; recarregar limpa tudo. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/" className={buttonClass("secondary", "lg")}>
          Ir para o início
        </a>
      </div>
      {digest && <p className="mt-6 text-foot text-ink-2">Código do erro: {digest}</p>}
    </PageFrame>
  );
}
