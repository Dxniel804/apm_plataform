import Link from "next/link";
import { ApiStatusChip } from "@/components/status/ApiStatusChip";
import { ChevronRightIcon } from "@/components/ui/icons";
import { Wordmark } from "@/components/ui/Logo";

const DEMOS = [
  {
    href: "/escola/demo-aurora",
    title: "Contribuir como família",
    text: "Portal da Escola Aurora (demo): do valor ao QR Code do Pix e ao comprovante.",
    featured: false,
  },
  {
    href: "/escola/demo-horizonte",
    title: "Outra escola",
    text: "Escola Horizonte (demo), com a sua própria configuração.",
    featured: false,
  },
  {
    href: "/login",
    title: "Entrar na gestão",
    text: "Painel da escola com o extrato do mês, para quem cuida das contas.",
    featured: true,
  },
] as const;

export default function HomePage() {
  return (
    <div className="halftone min-h-dvh">
      {/* Cabecalho de altura fixa: no celular o chip tem a propria linha (reservada), entao a API fora do ar
            ou voltando nunca empurra o titulo. */}
      <header className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-5 pb-2 pt-5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:px-8 sm:pt-7">
        <Wordmark width={120} />
        <ApiStatusChip />
      </header>

      <main id="conteudo" tabIndex={-1} className="mx-auto w-full max-w-6xl px-5 pb-16 pt-8 outline-none sm:px-8 lg:pt-16">
        <h1 className="mt-5 max-w-[17ch] text-balance text-hero sm:max-w-[20ch]">
          Contribuir com a APM leva um minuto. Prestar contas, também.
        </h1>
        <p className="mt-5 max-w-[46ch] text-body text-ink-2 sm:text-[1.1875rem]">
          Famílias pagam por Pix pelo celular, sem criar conta. A gestão acompanha cada contribuição, despesa e
          reembolso no mesmo lugar.
        </p>

        <h2 className="mb-4 mt-12 text-headline">Veja funcionando</h2>
        <ul className="grid gap-4 lg:grid-cols-3">
          {DEMOS.map((demo) => (
            <li key={demo.href}>
              <Link
                href={demo.href}
                className={`group flex h-full min-h-40 flex-col justify-between gap-6 rounded-[var(--r-lg)] border p-6 transition-colors ${
                  demo.featured
                    ? "border-transparent bg-grad-brand text-white hover:brightness-[1.06]"
                    : "border-line bg-white hover:border-brand-500 hover:bg-info-soft/50"
                }`}
              >
                <span>
                  <span className={`block text-[1.25rem] font-bold leading-snug ${demo.featured ? "text-white" : "text-brand-800"}`}>
                    {demo.title}
                  </span>
                  <span className={`mt-1 block text-sub ${demo.featured ? "text-white/90" : "text-ink-2"}`}>{demo.text}</span>
                </span>
                <span
                  aria-hidden="true"
                  className={`grid size-10 place-items-center self-end rounded-full ${demo.featured ? "bg-white/20 text-white" : "bg-info-soft text-brand-800"}`}
                >
                  <ChevronRightIcon size={20} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </main>

      <footer className="mx-auto w-full max-w-6xl px-5 pb-10 sm:px-8">
        <p className="max-w-[60ch] text-foot text-ink-2">
          Versão de demonstração com dados de exemplo. Em desenvolvimento o Pix é um sandbox: nenhum pagamento
          de verdade é feito.
        </p>
      </footer>
    </div>
  );
}
