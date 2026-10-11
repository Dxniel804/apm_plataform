import { formatBRL, formatBRLNumber } from "@/lib/money";

/**
 * Valor em reais no estilo do Figma: o "R$" em outra cor (preto) e o numero em azul (a cor vem do
 * texto do pai). Quem usa leitor de tela ouve o valor inteiro uma vez ("R$ 2.358,58"): a versao visual e
 * escondida dele e a versao falada fica fora da tela.
 */
export function Amount({
  cents,
  className = "",
  symbolClassName = "text-black",
}: {
  cents: number;
  className?: string;
  symbolClassName?: string;
}) {
  const text = formatBRLNumber(cents);
  const negative = text.startsWith("-");
  return (
    <span className={className}>
      <span className="sr-only">{formatBRL(cents)}</span>
      <span aria-hidden="true" className="whitespace-nowrap">
        {negative ? "-" : ""}
        <span className={symbolClassName}>R$</span> {negative ? text.slice(1) : text}
      </span>
    </span>
  );
}
