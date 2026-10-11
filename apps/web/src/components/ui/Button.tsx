import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";

/**
 * Botoes do Figma:
 *  - primary: degrade azul escuro -> azul vivo (Entrar, Salvar, item ativo do menu);
 *  - solid: azul escuro chapado (Continuar do fluxo da familia);
 *  - secondary: branco com borda (Voltar, Cancelar);
 *  - chip: pilula com degrade mais curto (Detalhes, filtro ativo, mes);
 *  - plain: so texto azul.
 */
type Variant = "primary" | "solid" | "secondary" | "chip" | "plain";
type Size = "md" | "lg";

const base =
  "inline-flex select-none items-center justify-center gap-2 px-5 font-bold tracking-[-0.005em] " +
  "transition-[transform,background-color,opacity,filter] duration-150 ease-out " +
  "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45";

const variants: Record<Variant, string> = {
  primary: "rounded-ctl bg-grad-brand text-white hover:brightness-[1.08]",
  solid: "rounded-ctl bg-brand-800 text-white hover:bg-brand-900",
  secondary: "rounded-ctl border border-field-border bg-white text-brand-800 hover:bg-info-soft",
  chip: "rounded-full bg-grad-chip text-white hover:brightness-[1.1]",
  plain: "rounded-ctl text-brand-800 hover:bg-info-soft",
};

const sizes: Record<Size, string> = {
  md: "min-h-11 text-sub",
  lg: "min-h-14 text-body sm:min-h-[3.75rem]",
};

export function buttonClass(variant: Variant = "primary", size: Size = "lg", extra = ""): string {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`.trim();
}

/** Filtros e abas em pilula (Figma "Despesas"): ativo em degrade, inativo cinza com borda. */
export function chipClass(active: boolean, extra = ""): string {
  return (
    "inline-flex min-h-11 select-none items-center justify-center rounded-full border px-5 text-sub font-medium transition-colors " +
    (active
      ? "border-transparent bg-grad-chip text-white "
      : "border-[#a7a7a7]/70 bg-chip/70 text-ink hover:bg-chip ") +
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
