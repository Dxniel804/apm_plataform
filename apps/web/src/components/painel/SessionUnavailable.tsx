import { ButtonLink, buttonClass } from "@/components/ui/Button";
import { PageFrame } from "@/components/ui/PageFrame";

/** O servidor nao conseguiu confirmar a sessao (API fora do ar ou resposta inesperada). Nao e logout. */
export function SessionUnavailable() {
  return (
    <PageFrame logoHref={null}>
      <h1 className="text-title sm:text-[2.25rem]">Não foi possível abrir o painel</h1>
      <p role="alert" className="mt-2 text-body text-ink-2">
        Não conseguimos confirmar a sua sessão agora. Isso não encerra o seu acesso. Tente de novo em instantes.
      </p>
      {/* <a> e nao <Link>: recarregar a pagina refaz a consulta no servidor. */}
      <a href="/painel" className={buttonClass("primary", "lg", "mt-6 self-start")}>
        Tentar de novo
      </a>
      <ButtonLink href="/login" variant="plain" size="md" className="mt-2 self-start">
        Ir para a entrada
      </ButtonLink>
    </PageFrame>
  );
}
