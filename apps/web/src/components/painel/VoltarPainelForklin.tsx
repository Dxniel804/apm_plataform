// Link discreto, no canto superior direito, que leva de volta ao painel (App) do Forklin, na mesma aba.

export function VoltarPainelForklin({ href }: { href: string }) {
  return (
    <a
      href={href}
      aria-label="Voltar para o painel Forklin"
      title="Voltar para o painel Forklin"
      className="inline-flex shrink-0 items-center gap-2 rounded-full bg-[#1e3a8a] py-1.5 pl-3.5 pr-3 text-xs font-medium leading-none text-white no-underline transition-colors hover:bg-[#1e40af] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#4f5bf5]"
    >
      <span className="hidden sm:inline">Voltar para o painel</span>
      <span className="sm:hidden">Painel</span>
      {/* A imagem traz a marca e a escrita "forklin"; abaixo de 640px so a marca aparece (recorte). */}
      <span aria-hidden="true" className="block h-5 w-5 overflow-hidden sm:w-[78px]">
        {/* eslint-disable-next-line @next/next/no-img-element -- arte fixa e pequena, sem otimizacao necessaria */}
        <img src="/forklin-logo-voltar.png" alt="" width={78} height={20} className="h-5 max-w-none" />
      </span>
    </a>
  );
}
