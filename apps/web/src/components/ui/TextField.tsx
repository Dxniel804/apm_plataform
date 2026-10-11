import { useId, type InputHTMLAttributes, type Ref, type SelectHTMLAttributes } from "react";
import { ChevronExpandIcon, InfoIcon } from "./icons";

/**
 * Campos do Figma. `outline` (modal da tesouraria e fluxo da familia): branco com borda cinza e cantos
 * de 18 px. `filled` (login): cinza claro sem borda. Com 16 px de fonte o iOS nao da zoom ao focar.
 */
type FieldVariant = "outline" | "filled";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  optional?: boolean;
  hint?: string;
  error?: string;
  inputRef?: Ref<HTMLInputElement>;
  /** Texto fixo antes do valor (ex.: "R$"). */
  prefix?: string;
  variant?: FieldVariant;
}

const skin: Record<FieldVariant, string> = {
  outline: "bg-white",
  filled: "bg-field",
};

function borderFor(variant: FieldVariant, error?: string) {
  if (error) return "border-bad";
  return variant === "filled" ? "border-transparent" : "border-field-border";
}

export function fieldClass(variant: FieldVariant = "outline") {
  return (
    `block w-full min-h-14 sm:min-h-[3.75rem] rounded-ctl border px-4 text-[1rem] text-ink placeholder:text-ink-3 transition-colors ` +
    `focus:border-brand-600 ${skin[variant]}`
  );
}

function Label({ htmlFor, label, optional, variant }: { htmlFor: string; label: string; optional?: boolean; variant: FieldVariant }) {
  return (
    <label
      htmlFor={htmlFor}
      className={`mb-2 block ${variant === "filled" ? "text-body font-semibold text-ink" : "text-sub font-bold text-brand-800"}`}
    >
      {label}
      {optional && <span className="font-medium text-ink-3"> (opcional)</span>}
    </label>
  );
}

function FieldError({ id, error }: { id: string; error?: string }) {
  return (
    <div aria-live="polite">
      {error && (
        <p id={id} className="mt-1.5 flex items-start gap-1.5 text-sub font-medium text-bad">
          <InfoIcon size={18} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({
  label,
  optional,
  hint,
  error,
  inputRef,
  prefix,
  variant = "outline",
  className = "",
  ...rest
}: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  const border = borderFor(variant, error);

  return (
    <div className={className}>
      <Label htmlFor={id} label={label} optional={optional} variant={variant} />
      {prefix ? (
        <div
          className={`flex min-h-14 items-center gap-2 rounded-ctl border px-4 sm:min-h-[3.75rem] ${skin[variant]} ${border} focus-within:border-brand-600 focus-within:outline focus-within:outline-[3px] focus-within:outline-offset-2 focus-within:outline-[var(--focus)]`}
        >
          <span aria-hidden="true" className="text-[1rem] font-semibold text-ink-2">
            {prefix}
          </span>
          <input
            id={id}
            ref={inputRef}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className="min-h-[52px] w-full bg-transparent text-[1rem] tabular-nums text-ink outline-none placeholder:text-ink-3"
            {...rest}
          />
        </div>
      ) : (
        <input
          id={id}
          ref={inputRef}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`${fieldClass(variant)} ${border}`}
          {...rest}
        />
      )}
      {hint && (
        <p id={hintId} className="mt-1.5 text-foot text-ink-2">
          {hint}
        </p>
      )}
      <FieldError id={errorId} error={error} />
    </div>
  );
}

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: string;
  /** Aparece no id do elemento (os testes e os rotulos usam). */
  id: string;
  optional?: boolean;
  error?: string;
  variant?: FieldVariant;
  wrapperClassName?: string;
}

/** Lista suspensa no mesmo molde dos campos, com as setas do Figma (chevron-expand). */
export function SelectField({
  label,
  id,
  optional,
  error,
  variant = "outline",
  wrapperClassName = "",
  className = "",
  children,
  ...rest
}: SelectFieldProps) {
  const errorId = `${id}-error`;
  return (
    <div className={wrapperClassName}>
      <Label htmlFor={id} label={label} optional={optional} variant={variant} />
      <div className="relative">
        <select
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className={`${fieldClass(variant)} ${borderFor(variant, error)} appearance-none pr-12 ${className}`}
          {...rest}
        >
          {children}
        </select>
        <ChevronExpandIcon
          size={20}
          className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-brand-800"
        />
      </div>
      <FieldError id={errorId} error={error} />
    </div>
  );
}
