import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";

/**
 * Botoes (visual Paper v2, sem degrade):
 *  - primary / solid: azul base chapado (Entrar, Continuar, Salvar);
 *  - secondary: branco com borda azulada (Voltar, Cancelar);
 *  - chip: pilula azul base (Detalhes, mes, acoes curtas);
 *  - plain: so texto azul.
 */
type Variant = "primary" | "solid" | "secondary" | "chip" | "plain";
type Size = "md" | "lg";

const base =
  "inline-flex select-none items-center justify-center gap-2 px-5 font-semibold tracking-[-0.003em] " +
  "transition-[transform,background-color,opacity,filter] duration-150 ease-out " +
  "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45";

const variants: Record<Variant, string> = {
  primary: "rounded-ctl bg-brand-800 text-white hover:brightness-[1.12]",
  solid: "rounded-ctl bg-brand-800 text-white hover:brightness-[1.12]",
  secondary: "rounded-ctl border-[1.5px] border-line-strong bg-white text-brand-800 hover:bg-info-soft",
  chip: "rounded-full bg-brand-800 text-white hover:brightness-[1.12]",
  plain: "rounded-ctl text-brand-800 hover:bg-info-soft",
};

const sizes: Record<Size, string> = {
  md: "min-h-11 text-sub",
  lg: "min-h-14 text-[1rem]",
};

export function buttonClass(variant: Variant = "primary", size: Size = "lg", extra = ""): string {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`.trim();
}

/** Filtros e abas em pilula: ativa em azul claro com borda, inativa branca com borda. */
export function chipClass(active: boolean, extra = ""): string {
  return (
    "inline-flex min-h-10 select-none items-center justify-center gap-2 rounded-full border px-4 text-sub transition-colors " +
    (active
      ? "border-pill-line bg-pill font-semibold text-brand-800 "
      : "border-line-strong bg-white font-normal text-ink-2 hover:bg-info-soft ") +
    extra
  ).trim();
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size };

export function Button({ variant = "primary", size = "lg", className = "", type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}

type ButtonLinkProps = ComponentProps<typeof Link> & { variant?: Variant; size?: Size };

export function ButtonLink({ variant = "primary", size = "lg", className = "", ...rest }: ButtonLinkProps) {
  return <Link className={buttonClass(variant, size, className)} {...rest} />;
}
