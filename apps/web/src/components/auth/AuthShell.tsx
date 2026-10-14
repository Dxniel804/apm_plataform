import Link from "next/link";
import type { ReactNode } from "react";
import { BagIcon, BankIcon, CalendarCheckIcon, Cart4Icon } from "@/components/ui/icons";
import { Wordmark } from "@/components/ui/Logo";
import { SchoolScene, SchoolSceneMini } from "./SchoolScene";

const FEATURES = [
  { icon: <BankIcon size={20} />, title: "Contribuições por Pix", text: "As famílias pagam sem criar conta e recebem o comprovante." },
  { icon: <Cart4Icon size={20} />, title: "Despesas com aprovação", text: "Anexe a nota, aprove, peça correção ou recuse." },
  { icon: <BagIcon size={20} />, title: "Campanhas da escola", text: "Produtos, carrinho e controle de entrega pela gestão." },
  { icon: <CalendarCheckIcon size={20} />, title: "Fechamento e relatórios", text: "Saldo do mês e PDF prontos para a prestação de contas." },
];

/**
 * Moldura das telas de acesso (login e convite), visual Paper v2. No computador: o formulario a esquerda e,
 * a direita, o painel azul com a curva, "Sobre" e "Recursos" e a escola em ilustracao. No celular: um
 * cabecalho azul com a escola em miniatura e o formulario numa folha branca de cantos arredondados.
 */
export function AuthShell({ title, eyebrow, children }: { title: string; eyebrow?: string; children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-white lg:grid lg:grid-cols-[minmax(0,36rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,40rem)_minmax(0,1fr)]">
      {/* celular: cabecalho azul */}
      <header className="relative h-[16.25rem] overflow-hidden bg-brand-600 lg:hidden">
        <SchoolSceneMini className="absolute inset-0 size-full" />
        <div className="relative px-6 pt-11">
          <Link href="/" className="inline-flex min-h-11 items-center">
            <Wordmark tone="white" width={108} priority />
          </Link>
          <p className="mt-5 max-w-[12rem] text-[1rem] font-semibold leading-snug text-white">
            Pix com comprovante e prestação de contas, no mesmo lugar.
          </p>
        </div>
      </header>

      <div className="relative z-10 -mt-7 flex flex-col rounded-t-[2rem] bg-white px-6 pb-10 pt-7 lg:mt-0 lg:min-h-dvh lg:rounded-none lg:px-14 lg:py-12 xl:px-[4.5rem]">
        <header className="mb-8 hidden lg:block">
          <Link href="/" className="inline-flex min-h-11 items-center">
            <Wordmark width={120} priority />
          </Link>
        </header>
        <main id="conteudo" tabIndex={-1} className="w-full max-w-[25rem] outline-none lg:my-auto">
          {eyebrow && <p className="text-[1rem] text-ink-2">{eyebrow}</p>}
          <h1 className="text-[clamp(1.875rem,1.5rem+1.2vw,2.5rem)] font-bold leading-[1.08] tracking-[-0.02em] text-brand-800">{title}</h1>
          {children}
        </main>
      </div>

      {/* computador: painel azul */}
      <aside className="relative hidden overflow-hidden lg:-ml-20 lg:block">
        <svg aria-hidden="true" focusable="false" viewBox="0 0 880 900" preserveAspectRatio="none" className="absolute inset-0 size-full">
          <path d="M200 0C120 150 30 300 60 450C90 600 260 720 230 900L880 900L880 0Z" fill="#346ae3" />
        </svg>
        <SchoolScene className="absolute bottom-0 right-0 w-[min(100%,41.75rem)] [@media(max-height:820px)]:hidden" />
        <div className="relative hidden pl-[15rem] pr-10 pt-[4.25rem] text-white xl:block 2xl:pl-[17.5rem]">
          <div className="max-w-[30rem]">
          <h2 className="text-[1.5rem] font-semibold leading-tight tracking-[-0.01em] text-white">Sobre a APM Digital</h2>
          <p className="mt-3 text-[0.9375rem] leading-relaxed">
            Contribuições por Pix, com comprovante, e a prestação de contas da gestão no mesmo lugar. Feito para a diretoria e para quem cuida do
            caixa da associação, com as famílias vendo para onde vai cada real.
          </p>
          <h2 className="mt-8 text-[1.5rem] font-semibold leading-tight tracking-[-0.01em] text-white">Recursos</h2>
          <ul className="mt-5 space-y-[1.125rem]">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="flex items-start gap-4">
                <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/20 text-white">
                  {feature.icon}
                </span>
                <span>
                  <span className="block text-[1rem] font-semibold leading-snug text-white">{feature.title}</span>
                  <span className="block text-sub leading-snug text-white">{feature.text}</span>
                </span>
              </li>
            ))}
          </ul>
          </div>
        </div>
      </aside>
    </div>
  );
}
