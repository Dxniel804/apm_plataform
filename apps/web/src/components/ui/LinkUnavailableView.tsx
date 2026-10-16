import Image from "next/image";
import type { ReactNode } from "react";
import { PageFrame } from "@/components/ui/PageFrame";
import { ClockIcon, LockIcon, SchoolIcon } from "@/components/ui/icons";

function Reason({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <li className="rounded-[var(--r-md)] border border-line bg-white p-4 text-left">
      <span aria-hidden="true" className="grid size-9 place-items-center rounded-full bg-info-soft text-brand-800">
        {icon}
      </span>
      <h2 className="mt-3 text-sub font-semibold">{title}</h2>
      <p className="mt-1 text-foot text-ink-2">{children}</p>
    </li>
  );
}

/**
 * O link publico de uma escola que ainda nao abre (sem recebimento configurado) e o de um endereco errado: a MESMA tela,
 * para nunca confirmar nem negar a existencia de uma escola (ADR-010). Fala com a familia, sem "404".
 */
export function LinkUnavailableView() {
  return (
    <PageFrame size="wide" logoHref={null}>
      <div className="mx-auto flex w-full max-w-3xl flex-col items-center text-center">
        {/* Arte com fundo transparente (webp com alfa), recortada na borda do desenho. */}
        <Image
          src="/brand/pagamento-indisponivel.webp"
          alt=""
          width={1000}
          height={664}
          priority
          className="h-auto w-full max-w-[24rem] select-none"
        />
        <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-info-soft px-3 py-1 text-foot font-medium text-info">
          <ClockIcon size={16} />
          Link em preparação
        </p>
        <h1 className="mt-4 max-w-[22ch] text-balance text-title sm:text-[2.25rem]">Esta página ainda não está disponível</h1>
        <p className="mt-3 max-w-[46ch] text-body text-ink-2">
          Este link ainda não está aberto para contribuições. Se a gestão da APM enviou este endereço, ele pode abrir em breve.
        </p>
        <ul className="mt-8 grid w-full gap-3 sm:grid-cols-3">
          <Reason icon={<SchoolIcon size={18} />} title="O que está acontecendo">
            O link só abre quando a gestão da APM termina de configurar o recebimento de contribuições por Pix.
          </Reason>
          <Reason icon={<ClockIcon size={18} />} title="O que fazer">
            Tente de novo em alguns dias. Se o link foi enviado há pouco tempo, ele deve abrir em breve.
          </Reason>
          <Reason icon={<LockIcon size={18} />} title="Nada foi cobrado">
            Enquanto a página está fechada, nenhuma cobrança é feita. O Pix só existe depois que você confirma uma contribuição.
          </Reason>
        </ul>
        <p className="mt-6 max-w-[46ch] text-foot text-ink-2">
          Ficou com dúvida? Confirme o endereço do link com a gestão da APM da sua escola.
        </p>
      </div>
    </PageFrame>
  );
}
