import { useId, type InputHTMLAttributes } from "react";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type"> {
  label: string;
  /** Uma frase de apoio sob o rotulo. */
  hint?: string;
}

/** Caixa de marcar do painel: o rotulo inteiro e clicavel, a area de toque tem 44 px e o foco aparece. */
export function CheckboxField({ label, hint, className = "", ...rest }: Props) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={className}>
      <label htmlFor={id} className="flex min-h-11 cursor-pointer items-start gap-3 py-1">
        <input id={id} type="checkbox" aria-describedby={hint ? hintId : undefined} className="mt-0.5 size-6 shrink-0 cursor-pointer accent-[var(--brand-800)]" {...rest} />
        <span className="min-w-0">
          <span className="block text-sub font-semibold text-ink">{label}</span>
          {hint && (
            <span id={hintId} className="mt-0.5 block text-sub text-ink-2">
              {hint}
            </span>
          )}
        </span>
      </label>
    </div>
  );
}
