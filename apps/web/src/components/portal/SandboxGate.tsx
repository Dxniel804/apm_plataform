"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";

/**
 * Escola em ambiente de demonstracao (docs/adr-ambiente-sandbox.md): antes da tela de contribuicao a familia
 * le que os dados e o pagamento sao ficticios. So depois de "Entendi" a contribuicao aparece. Escola em
 * producao (ou sem a informacao da Central) nao passa por aqui: `active` e false e nada muda. O aviso volta
 * a cada abertura da pagina; nao e estado de negocio, e so esta tela.
 */
export function SandboxGate({ active, children }: { active: boolean; children: ReactNode }) {
  const [understood, setUnderstood] = useState(false);
  if (!active || understood) return <>{children}</>;
  return (
    <section className="-mx-4 flex flex-1 flex-col rounded-t-[var(--r-xl)] bg-white px-5 pt-6 sm:mx-0 sm:rounded-[var(--r-xl)] sm:border sm:border-line sm:p-8 lg:p-10">
      <div role="region" aria-labelledby="sandbox-gate-title" className="mx-auto w-full max-w-md py-4">
        <h1 id="sandbox-gate-title" className="text-heading text-ink">
          Ambiente de demonstração
        </h1>
        <p className="mt-3 text-body text-ink-2">
          Esta escola está em um ambiente de demonstração. Os dados que você vê e o pagamento são fictícios: nenhum
          dinheiro de verdade é cobrado nem recebido.
        </p>
        <p className="mt-3 text-body text-ink-2">Pode seguir e testar a contribuição, inclusive o Pix, à vontade.</p>
        <Button className="mt-6 w-full" onClick={() => setUnderstood(true)}>
          Entendi, continuar
        </Button>
      </div>
    </section>
  );
}
