import { useId, type InputHTMLAttributes, type ReactNode, type Ref, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { ChevronExpandIcon, InfoIcon } from "./icons";

/**
 * Campos do Figma. `outline` (modal da gestao e fluxo da familia): branco com borda cinza e cantos
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
  /** Icone decorativo dentro do campo, antes do valor. */
  icon?: ReactNode;
  /** Controle depois do valor, dentro do campo (ex.: mostrar/ocultar a senha). */
  trailing?: ReactNode;
  variant?: FieldVariant;
}

const skin: Record<FieldVariant, string> = {
  outline: "bg-white",
  filled: "bg-white",
};

function borderFor(variant: FieldVariant, error?: string) {
  if (error) return "border-bad";
  return "border-field-border";
}

export function fieldClass(variant: FieldVariant = "outline") {
  return (
    `block w-full min-h-[3.375rem] rounded-ctl border-[1.5px] px-4 text-[1rem] text-ink placeholder:text-ink-3 transition-colors ` +
    `focus:border-brand-600 ${skin[variant]}`
  );
}

function Label({ htmlFor, label, optional }: { htmlFor: string; label: string; optional?: boolean; variant?: FieldVariant }) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-2 block text-sub font-semibold text-ink"
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
  icon,
  trailing,
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
      {prefix || icon || trailing ? (
        <div
          className={`flex min-h-[3.375rem] items-center gap-2 rounded-ctl border-[1.5px] px-4 ${skin[variant]} ${border} focus-within:border-brand-600 focus-within:outline focus-within:outline-[3px] focus-within:outline-offset-2 focus-within:outline-[var(--focus)]`}
        >
          {icon && (
            <span aria-hidden="true" className="shrink-0 text-ink-3">
              {icon}
            </span>
          )}
          {prefix && (
            <span aria-hidden="true" className="text-[1rem] font-semibold text-ink-2">
              {prefix}
            </span>
          )}
          <input
            id={id}
            ref={inputRef}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={`min-h-[48px] w-full bg-transparent text-[1rem] text-ink outline-none placeholder:text-ink-3 ${prefix ? "tabular-nums" : ""}`}
            {...rest}
          />
          {trailing}
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

interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {
  label: string;
  optional?: boolean;
  hint?: string;
  error?: string;
  variant?: FieldVariant;
}

/** Texto de varias linhas no mesmo molde dos campos (descricao de uma solicitacao, resposta da gestao). */
export function TextAreaField({ label, optional, hint, error, variant = "outline", className = "", rows = 4, ...rest }: TextAreaFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={className}>
      <Label htmlFor={id} label={label} optional={optional} variant={variant} />
      <textarea
        id={id}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`block w-full resize-y rounded-ctl border-[1.5px] px-4 py-3.5 text-[1rem] text-ink placeholder:text-ink-3 transition-colors focus:border-brand-600 ${skin[variant]} ${borderFor(variant, error)}`}
        {...rest}
      />
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
