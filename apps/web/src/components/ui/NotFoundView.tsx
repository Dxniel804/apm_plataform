import { ButtonLink } from "@/components/ui/Button";
import { PageFrame } from "@/components/ui/PageFrame";

/** 404 estilizada. O texto nunca confirma nem nega a existencia de escolas ou pedidos (ADR-010). */
export function NotFoundView({ title, text }: { title: string; text: string }) {
  return (
    <PageFrame size="wide" logoHref={null}>
      <p
        aria-hidden="true"
        className="bg-grad-brand bg-clip-text text-[6.5rem] font-bold leading-none tracking-[-0.05em] text-transparent sm:text-[9rem]"
      >
        404
      </p>
      <h1 className="mt-2 max-w-[20ch] text-balance text-title sm:text-[2.5rem]">{title}</h1>
      <p className="mt-3 max-w-[46ch] text-body text-ink-2">{text}</p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <ButtonLink href="/" variant="solid">
          Ir para o início
        </ButtonLink>
        <ButtonLink href="/apm/escola-exemplo" variant="secondary">
          Ver a escola de exemplo
        </ButtonLink>
      </div>
    </PageFrame>
  );
}
