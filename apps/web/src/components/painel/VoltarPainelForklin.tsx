// Link discreto, no canto superior direito, que leva de volta ao painel (App) do Forklin, na mesma aba.

// O fundo e um degrade de largura dupla: em repouso mostra so a metade azul-escura (cor solida, como antes);
// no hover o fundo desliza para a outra metade e o azul vai clareando da esquerda para a direita.
export function VoltarPainelForklin({ href }: { href: string }) {
  return (
    <a
      href={href}
      aria-label="Voltar para o painel Forklin"
      title="Voltar para o painel Forklin"
      className="inline-flex shrink-0 items-center gap-3 rounded-full bg-[#1e3a8a] bg-[linear-gradient(90deg,#1e3a8a_0%,#1e3a8a_50%,#2f55d4_72%,#4f5bf5_100%)] bg-[length:200%_100%] bg-left py-2.5 pl-5 pr-4 text-sm font-semibold leading-none text-white no-underline shadow-sm transition-[background-position,box-shadow,transform] duration-500 ease-out hover:-translate-y-px hover:bg-right hover:shadow-lg focus-visible:bg-right focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#4f5bf5] motion-reduce:transition-none motion-reduce:hover:translate-y-0"
    >
      <span className="hidden sm:inline">Voltar para o painel</span>
      <span className="sm:hidden">Painel</span>
      {/* A imagem traz a marca e a escrita "forklin"; abaixo de 640px so a marca aparece (recorte). */}
      <span aria-hidden="true" className="block h-6 w-6 overflow-hidden sm:w-[94px]">
        {/* eslint-disable-next-line @next/next/no-img-element -- arte fixa e pequena, sem otimizacao necessaria */}
        <img src="/forklin-logo-voltar.png" alt="" width={94} height={24} className="h-6 max-w-none" />
      </span>
    </a>
  );
}
