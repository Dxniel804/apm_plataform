import { useMemo, useSyncExternalStore } from "react";

/**
 * Endereco `blob:` de um arquivo ou foto que o navegador ja tem em memoria, para mostrar uma previa. O endereco
 * e criado na primeira vez que alguem o usa e revogado quando ninguem mais usa (com uma folga de um ciclo, para
 * a remontagem do modo estrito do React nao quebrar a imagem). Nada sai do navegador.
 */
interface Entry {
  url: string;
  refs: number;
  timer: ReturnType<typeof setTimeout> | null;
}

const entries = new Map<Blob, Entry>();

function entryFor(blob: Blob): Entry | null {
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") return null;
  let entry = entries.get(blob);
  if (!entry) {
    entry = { url: URL.createObjectURL(blob), refs: 0, timer: null };
    entries.set(blob, entry);
  }
  return entry;
}

function subscriberFor(blob: Blob) {
  return () => {
    const entry = entryFor(blob);
    if (!entry) return () => {};
    entry.refs += 1;
    if (entry.timer) clearTimeout(entry.timer);
    entry.timer = null;
    return () => {
      entry.refs -= 1;
      if (entry.refs > 0) return;
      entry.timer = setTimeout(() => {
        if (entry.refs > 0) return;
        URL.revokeObjectURL(entry.url);
        entries.delete(blob);
      }, 0);
    };
  };
}

export function useObjectUrl(blob: Blob | null): string | null {
  const subscribe = useMemo(() => (blob ? subscriberFor(blob) : () => () => {}), [blob]);
  return useSyncExternalStore(
    subscribe,
    () => (blob ? (entryFor(blob)?.url ?? null) : null),
    () => null,
  );
}
