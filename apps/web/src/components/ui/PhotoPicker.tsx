"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { CameraDialog } from "@/components/ui/CameraDialog";
import { CameraIcon, ImageIcon, XLgIcon } from "@/components/ui/icons";
import { useObjectUrl } from "@/lib/hooks/useObjectUrl";
import { fitPhoto, isPhotoFile } from "@/lib/photo";
import { MAX_PHOTO_BYTES, MAX_PHOTOS } from "@/lib/request-labels";
import { formatFileSize } from "@/lib/expense-labels";

interface PhotoPickerProps {
  photos: File[];
  onChange: (photos: File[]) => void;
  /** Quantas fotos cabem (a API aceita 6 por solicitacao). */
  max?: number;
  disabled?: boolean;
  label?: string;
  /** Erro de quem usa o seletor (ex.: uma foto que o servidor recusou). */
  error?: string | null;
}

function Thumb({ file, index, onRemove, disabled }: { file: File; index: number; onRemove: () => void; disabled: boolean }) {
  const url = useObjectUrl(file);
  return (
    <li className="relative">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- previa local (blob:) de uma foto que ainda nem foi enviada
        <img src={url} alt={`Foto ${index + 1}`} className="aspect-square w-full rounded-[1rem] border border-line object-cover" />
      ) : (
        <span aria-hidden="true" className="grid aspect-square w-full place-items-center rounded-[1rem] border border-line bg-info-soft text-brand-800">
          <ImageIcon size={28} />
        </span>
      )}
      <span className="mt-1 block truncate text-foot text-ink-2">{formatFileSize(file.size)}</span>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remover foto ${index + 1}`}
        className="absolute right-1.5 top-1.5 grid size-9 place-items-center rounded-full bg-white/95 text-ink shadow hover:bg-white disabled:opacity-60"
      >
        <XLgIcon size={14} />
      </button>
    </li>
  );
}

/**
 * Fotos de uma solicitacao: tirar na hora (camera do navegador) ou escolher da galeria, com previa e "remover". As
 * fotos ficam so na memoria do navegador, reduzidas para caber no limite; quem usa o seletor envia pelo formulario.
 * Aceita PNG, JPEG e WebP (o servidor confere o tipo pelos bytes de novo).
 */
export function PhotoPicker({ photos, onChange, max = MAX_PHOTOS, disabled = false, label = "Fotos", error = null }: PhotoPickerProps) {
  const gallery = useRef<HTMLInputElement>(null);
  const capture = useRef<HTMLInputElement>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [local, setLocal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const full = photos.length >= max;

  async function add(files: File[]) {
    if (files.length === 0) return;
    setLocal(null);
    const problems: string[] = [];
    const accepted: File[] = [];
    setBusy(true);
    for (const file of files) {
      if (photos.length + accepted.length >= max) {
        problems.push(`Cabem no máximo ${max} fotos.`);
        break;
      }
      if (!isPhotoFile(file)) {
        problems.push(`“${file.name}” não é uma foto PNG, JPEG ou WebP.`);
        continue;
      }
      const fitted = await fitPhoto(file);
      if (fitted.size > MAX_PHOTO_BYTES) {
        problems.push(`“${file.name}” é grande demais (o limite é de 10 MB).`);
        continue;
      }
      accepted.push(fitted);
    }
    setBusy(false);
    if (accepted.length > 0) onChange([...photos, ...accepted]);
    if (problems.length > 0) setLocal(problems.join(" "));
  }

  const hasLiveCamera = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);

  return (
    <div>
      <p className="mb-2 text-sub font-bold text-brand-800">
        {label}
        <span className="font-medium text-ink-3"> (opcional, até {max})</span>
      </p>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          variant="chip"
          size="md"
          disabled={disabled || busy || full}
          onClick={() => (hasLiveCamera ? setCameraOpen(true) : capture.current?.click())}
          className="min-h-12 px-6"
        >
          <CameraIcon size={18} className="mr-2" />
          Tirar foto
        </Button>
        <Button variant="chip" size="md" disabled={disabled || busy || full} onClick={() => gallery.current?.click()} className="min-h-12 px-6">
          <ImageIcon size={18} className="mr-2" />
          Escolher da galeria
        </Button>
      </div>

      {/* Entradas escondidas: a galeria aceita varias; a segunda usa a camera do sistema quando o navegador nao tem getUserMedia. */}
      <input
        ref={gallery}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
        aria-label="Escolher fotos da galeria"
        onChange={(event) => {
          void add(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
      <input
        ref={capture}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        aria-label="Tirar foto com a câmera do aparelho"
        onChange={(event) => {
          void add(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />

      {busy && (
        <p role="status" className="mt-3 text-sub text-ink-2">
          Preparando a foto…
        </p>
      )}
      {photos.length > 0 && (
        <ul aria-label="Fotos escolhidas" className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {photos.map((file, index) => (
            <Thumb key={`${file.name}-${file.size}-${file.lastModified}-${index}`} file={file} index={index} disabled={disabled} onRemove={() => onChange(photos.filter((_, i) => i !== index))} />
          ))}
        </ul>
      )}
      {(local || error) && (
        <p role="alert" className="mt-3 text-sub font-medium text-bad">
          {local ?? error}
        </p>
      )}

      <CameraDialog
        open={cameraOpen}
        onClose={() => setCameraOpen(false)}
        onCapture={(photo) => {
          setCameraOpen(false);
          void add([photo]);
        }}
      />
    </div>
  );
}
