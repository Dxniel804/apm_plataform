"use client";

import { useEffect, useRef, useSyncExternalStore, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

const noopSubscribe = () => () => {};

/** Janelas abertas, da mais antiga para a mais nova. So a do topo trata o teclado (Esc e Tab): uma janela aberta
 *  por cima de outra (a camera sobre o formulario) nao pode fechar a de baixo nem roubar o foco dela. */
const openWindows: symbol[] = [];

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Nome acessivel da janela (aria-label). */
  label: string;
  children: ReactNode;
  /** `center`: janela no meio (folha de baixo no celular). `drawer`: gaveta encostada na esquerda. */
  placement?: "center" | "drawer";
  /** Quem recebe o foco ao abrir; sem isso, a propria janela. */
  initialFocus?: RefObject<HTMLElement | null>;
  className?: string;
}

/**
 * Janela modal acessivel: foco preso dentro dela, Esc e clique fora fecham, a rolagem da pagina fica
 * travada e o foco volta para quem abriu. Sem animacao de entrada que parta de fora da tela (o guarda
 * de CSS proibe): a janela so "cresce" um pouco, e so com o movimento ligado (MotionGate).
 */
export function Modal({ open, onClose, label, children, placement = "center", initialFocus, className = "" }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  // O portal so existe no navegador (sem setState em efeito).
  const isClient = useSyncExternalStore(noopSubscribe, () => true, () => false);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";

    (initialFocus?.current ?? panelRef.current)?.focus();

    const token = Symbol("modal");
    openWindows.push(token);

    const onKeyDown = (event: KeyboardEvent) => {
      if (openWindows[openWindows.length - 1] !== token) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0]!;
      const last = items[items.length - 1]!;
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      } else if (!panel.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      const at = openWindows.indexOf(token);
      if (at >= 0) openWindows.splice(at, 1);
      root.style.overflow = previousOverflow;
      opener?.focus?.();
    };
  }, [open, initialFocus]);

  if (!open || !isClient) return null;

  const drawer = placement === "drawer";
  return createPortal(
    <div
      className={`fixed inset-0 z-50 flex ${drawer ? "items-stretch justify-start" : "items-end justify-center sm:items-center sm:p-6"}`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[rgb(16_20_40/0.5)]" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className={`pop relative overflow-y-auto bg-white outline-none ${
          drawer
            ? "h-dvh w-[min(20rem,88vw)] rounded-r-[var(--r-lg)] shadow-[var(--shadow-sheet)]"
            : "max-h-dvh w-full rounded-t-[var(--r-xl)] shadow-[var(--shadow-sheet)] sm:max-h-[calc(100dvh-3rem)] sm:max-w-[44rem] sm:rounded-[var(--r-xl)]"
        } ${className}`}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
