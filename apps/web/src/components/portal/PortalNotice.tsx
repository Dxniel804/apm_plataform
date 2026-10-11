import { buttonClass } from "@/components/ui/Button";
import { PageFrame } from "@/components/ui/PageFrame";

/**
 * Tela amigavel do portal para o que nao e um 404: muitos acessos (429) ou API indisponivel.
 * Sem texto do servidor. O `<a>` recarrega a pagina (refaz a consulta no servidor).
 */
export function PortalNotice({ title, text, reloadHref }: { title: string; text: string; reloadHref: string }) {
  return (
    <PageFrame size="medium">
      <h1 className="text-title sm:text-[2.25rem]">{title}</h1>
      <p role="alert" className="mt-3 text-body text-ink-2">
        {text}
      </p>
      <a href={reloadHref} className={buttonClass("solid", "lg", "mt-7 self-start")}>
        Tentar de novo
      </a>
    </PageFrame>
  );
}
