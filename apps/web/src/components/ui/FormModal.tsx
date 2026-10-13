"use client";

import { useId, type ReactNode, type RefObject } from "react";
import { Button } from "@/components/ui/Button";
import { XLgIcon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";

interface WindowProps {
  title: string;
  /** Uma ou duas frases sob o titulo: o que este formulario faz. */
  intro?: ReactNode;
  onClose: () => void;
  /** Enquanto grava: o X nao fecha a janela (a pessoa nao perde o que esta sendo enviado). */
  busy?: boolean;
  children: ReactNode;
  /** Id do titulo, para quem precisa ligar o formulário a ele (`aria-labelledby`). */
  titleId?: string;
}

/**
 * O MODELO de todo formulario do painel: o mesmo de "Registrar contribuicao em dinheiro". Uma janela com o
 * halftone da marca no pe, o titulo grande, o X no canto, uma frase de apoio e, embaixo, "Cancelar" e o botao
 * principal lado a lado (`FormButtons`). Quem abre a janela (um `Modal`) e quem trata o teclado, o foco e o Esc.
 */
export function FormWindow({ title, intro, onClose, busy = false, children, titleId }: WindowProps) {
  const generated = useId();
  const id = titleId ?? generated;
  return (
    <div className="halftone relative px-5 pb-8 pt-6 sm:px-12 sm:pb-12 sm:pt-10">
      <div className="flex items-start justify-between gap-4">
        <h2 id={id} className="text-[clamp(1.5rem,1.1rem+1.4vw,2.25rem)] font-semibold leading-tight tracking-[-0.015em]">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Fechar a janela"
          className="-mr-2 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink-3 hover:bg-info-soft"
        >
          <XLgIcon size={22} />
        </button>
      </div>
      {intro && <p className="mt-2 max-w-[60ch] text-body text-ink-2">{intro}</p>}
      <div className="mt-7">{children}</div>
    </div>
  );
}

interface ModalProps extends Omit<WindowProps, "children" | "titleId"> {
  /** Padrao: aberta. Quem so mostra a janela de vez em quando pode deixar o componente fora da tela. */
  open?: boolean;
  initialFocus?: RefObject<HTMLElement | null>;
  children: ReactNode;
}

/** `Modal` + `FormWindow`: a janela de formulario completa. O nome acessivel da janela e o proprio titulo. */
export function FormModal({ open = true, title, intro, onClose, busy = false, initialFocus, children }: ModalProps) {
  return (
    <Modal open={open} onClose={() => !busy && onClose()} label={title} initialFocus={initialFocus}>
      <FormWindow title={title} intro={intro} onClose={onClose} busy={busy}>
        {children}
      </FormWindow>
    </Modal>
  );
}

interface ButtonsProps {
  onCancel: () => void;
  cancelLabel?: string;
  submitLabel: string;
  pendingLabel?: string;
  pending?: boolean;
  /** Desliga o botao principal sem ser por estar gravando (ex.: nada para salvar). */
  disabled?: boolean;
  /** Botoes a mais (ex.: "Salvar rascunho" ao lado de "Salvar e enviar"): ficam entre os dois. */
  children?: ReactNode;
}

/** O rodape do modelo: "Cancelar" (ou "Fechar") e o botao principal, lado a lado no desktop e empilhados no celular. */
export function FormButtons({ onCancel, cancelLabel = "Cancelar", submitLabel, pendingLabel = "Salvando…", pending = false, disabled = false, children }: ButtonsProps) {
  return (
    <div className={`grid gap-3 pt-3 ${children ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
      <Button variant="secondary" onClick={onCancel} disabled={pending} className="rounded-full! order-last sm:order-1">
        {cancelLabel}
      </Button>
      {children}
      <Button type="submit" disabled={pending || disabled} aria-busy={pending} className="rounded-full! order-1 sm:order-3">
        {pending ? pendingLabel : submitLabel}
      </Button>
    </div>
  );
}
