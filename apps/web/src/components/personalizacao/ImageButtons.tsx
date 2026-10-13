"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ImageIcon } from "@/components/ui/icons";
import { MAX_IMAGE_BYTES } from "@/lib/campaign-labels";
import { fitPhoto, isPhotoFile } from "@/lib/photo";

interface Props {
  /** Para o nome acessivel: "capa" ou "imagem do produto Pamonha". */
  what: string;
  hasImage: boolean;
  disabled: boolean;
  /** Envia a imagem; devolve o texto do erro, ou null se deu certo. */
  onUpload: (file: File) => Promise<string | null>;
  onRemove: () => Promise<void>;
}

/** Escolher (da galeria ou do computador) e remover a imagem. A imagem e reduzida no navegador antes de subir. */
export function ImageButtons({ what, hasImage, disabled, onUpload, onRemove }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose(file: File | undefined) {
    if (!file || busy) return;
    setError(null);
    if (!isPhotoFile(file)) return setError("Escolha uma imagem PNG, JPEG ou WebP.");
    setBusy(true);
    const fitted = await fitPhoto(file, { maxSide: 1600 });
    if (fitted.size > MAX_IMAGE_BYTES) {
      setBusy(false);
      return setError("A imagem é grande demais. O limite é de 5 MB.");
    }
    const problem = await onUpload(fitted);
    setBusy(false);
    if (problem) setError(problem);
  }

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" size="md" onClick={() => input.current?.click()} disabled={disabled || busy} aria-label={`${hasImage ? "Trocar" : "Escolher"} ${what}`} className="rounded-full!">
          <ImageIcon size={18} className="mr-1" />
          {busy ? "Enviando…" : hasImage ? "Trocar imagem" : "Escolher imagem"}
        </Button>
        {hasImage && (
          <Button
            variant="plain"
            size="md"
            onClick={() => {
              setError(null);
              setBusy(true);
              void onRemove().finally(() => setBusy(false));
            }}
            disabled={disabled || busy}
            aria-label={`Remover ${what}`}
            className="rounded-full!"
          >
            Remover
          </Button>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        aria-label={`Arquivo da ${what}`}
        onChange={(event) => {
          void choose(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      {error && (
        <p role="alert" className="mt-2 text-sub font-medium text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
