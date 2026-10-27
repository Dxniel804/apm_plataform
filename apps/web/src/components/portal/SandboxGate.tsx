"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";

/**
 * Escola em ambiente de demonstracao (docs/adr-ambiente-sandbox.md): antes da tela de contribuicao a familia
 * le que os dados e o pagamento sao ficticios. So depois de "Entendi" a contribuicao aparece. Escola em
 * producao (ou sem a informacao da Central) nao passa por aqui: `active` e false e nada muda. O aviso volta
 * a cada abertura da pagina; nao e estado de negocio, e so esta tela. Card pequeno, centrado, so com o aviso.
 */
export function SandboxGate({ active, children }: { active: boolean; children: ReactNode }) {
  const [understood, setUnderstood] = useState(false);
  if (!active || understood) return <>{children}</>;
  return (
    <section className="flex flex-1 items-center justify-center py-8">
      <div
        role="region"
        aria-labelledby="sandbox-gate-title"
        className="w-full max-w-sm rounded-[var(--r-xl)] border border-line bg-white p-6 text-center shadow-sm sm:p-7"
      >
        <h1 id="sandbox-gate-title" className="text-heading text-ink">
          Ambiente de demonstração
        </h1>
        <p className="mt-3 text-body text-ink-2">
          Esta escola está em um ambiente de demonstração. Os dados que você vê e o pagamento são fictícios: nenhum
          dinheiro de verdade é cobrado nem recebido.
        </p>
        {/* Hover: o botão sobe um pouco e ganha sombra; ao clicar, volta (active do Button). */}
        <Button
          className="mt-6 w-full hover:-translate-y-0.5 hover:shadow-lg motion-reduce:hover:translate-y-0"
          onClick={() => setUnderstood(true)}
        >
          Entendi, continuar
        </Button>
      </div>
    </section>
  );
}
