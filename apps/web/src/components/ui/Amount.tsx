import { formatBRL, formatBRLNumber } from "@/lib/money";

/**
 * Valor em reais: o "R$" pode ter outra cor (`symbolClassName`) e os centavos outro tamanho
 * (`centsClassName`, estilo "R$ 2.358,58" com os centavos menores); a cor vem do texto do pai. Quem usa leitor de tela ouve o valor inteiro uma vez ("R$ 2.358,58"): a versao visual e
 * escondida dele e a versao falada fica fora da tela.
 */
export function Amount({
  cents,
  className = "",
  symbolClassName = "",
  centsClassName,
}: {
  cents: number;
  className?: string;
  symbolClassName?: string;
  centsClassName?: string;
}) {
  const text = formatBRLNumber(cents);
  const negative = text.startsWith("-");
  const body = negative ? text.slice(1) : text;
  const [whole = "", fraction = ""] = body.split(",");
  return (
    <span className={className}>
      <span className="sr-only">{formatBRL(cents)}</span>
      <span aria-hidden="true" className="whitespace-nowrap">
        {negative ? "-" : ""}
        <span className={symbolClassName}>R$</span>{" "}
        {centsClassName ? (
          <>
            {whole}
            <span className={centsClassName}>,{fraction}</span>
          </>
        ) : (
          body
        )}
      </span>
    </span>
  );
}
