import Image from "next/image";

// Proporcao do arquivo do logo ja aparado (560 x 153).
const RATIO = 153 / 560;

interface WordmarkProps {
  /** `dark` para fundos claros; `white` para o painel azul do login. */
  tone?: "dark" | "white";
  /** Largura em px (a altura segue a proporcao do arquivo). */
  width?: number;
  className?: string;
  priority?: boolean;
}

/** Logo "fknelo": as letras do Figma, com o arco (pais, mestres e o aluno) no lugar do "n". Arquivos em /public/brand; fonte em docs/brand. */
export function Wordmark({ tone = "dark", width = 132, className = "", priority = false }: WordmarkProps) {
  return (
    <Image
      src={tone === "white" ? "/brand/fknelo-white.png" : "/brand/fknelo-dark.png"}
      alt="fknelo"
      width={width}
      height={Math.round(width * RATIO)}
      priority={priority}
      // self-center + h-auto: dentro de um contêiner flex/grid o logo mantem a proporcao (antes esticava na vertical).
      className={`h-auto select-none self-center object-contain ${className}`.trim()}
      style={{ width }}
    />
  );
}

/** So o simbolo (o arco com o ponto), para onde nao cabe o nome: menu recolhido, selos. */
export function Mark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <Image
      src="/brand/mark.png"
      alt="fknelo"
      width={size}
      height={size}
      className={`select-none self-center object-contain ${className}`.trim()}
      style={{ width: size, height: size }}
    />
  );
}
