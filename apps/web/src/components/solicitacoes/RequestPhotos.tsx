"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ImageIcon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import type { RequestPhoto } from "@/lib/api/types";
import { saveBlob } from "@/lib/download";
import { formatFileSize } from "@/lib/expense-labels";
import { useObjectUrl } from "@/lib/hooks/useObjectUrl";
import { describeRequestError } from "@/lib/request-labels";

interface Props {
  schoolId: string;
  requestId: string;
  photos: RequestPhoto[];
}

function Photo({ schoolId, requestId, photo, index }: { schoolId: string; requestId: string; photo: RequestPhoto; index: number }) {
  const [state, setState] = useState<{ blob: Blob | null; error: string | null } | null>(null);
  const [open, setOpen] = useState(false);
  const url = useObjectUrl(state?.blob ?? null);

  useEffect(() => {
    let cancelled = false;
    void api.requests.download(schoolId, requestId, photo.id).then((result) => {
      if (cancelled) return;
      setState(result.ok ? { blob: result.data.blob, error: null } : { blob: null, error: describeRequestError(result.error).general });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, requestId, photo.id]);

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={!url}
        aria-label={`Ver foto ${index + 1} em tamanho maior`}
        className="block w-full overflow-hidden rounded-[1rem] border border-line bg-info-soft text-brand-800 hover:border-brand-600 disabled:cursor-default"
      >
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- foto baixada pela API com a sessao (blob:), sem URL publica
          <img src={url} alt={`Foto ${index + 1}`} className="aspect-square w-full object-cover" />
        ) : (
          <span className="grid aspect-square w-full place-items-center">
            {state?.error ? <span className="px-2 text-center text-foot text-bad">Foto indisponível</span> : <ImageIcon size={28} aria-hidden="true" />}
          </span>
        )}
      </button>
      <Modal open={open} onClose={() => setOpen(false)} label={`Foto ${index + 1}`}>
        <div className="p-4 sm:p-6">
          {url && (
            // eslint-disable-next-line @next/next/no-img-element -- idem
            <img src={url} alt={`Foto ${index + 1}`} className="mx-auto max-h-[70dvh] w-auto max-w-full rounded-[1rem] object-contain" />
          )}
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sub text-ink-2">
              {photo.fileName} · {formatFileSize(photo.sizeBytes)}
            </p>
            <div className="flex gap-3">
              {state?.blob && (
                <Button variant="secondary" size="md" onClick={() => saveBlob(state.blob as Blob, photo.fileName)} className="rounded-full!">
                  Baixar
                </Button>
              )}
              <Button size="md" onClick={() => setOpen(false)} className="rounded-full!">
                Fechar
              </Button>
            </div>
          </div>
        </div>
      </Modal>
    </li>
  );
}

/** As fotos de uma solicitacao, baixadas pela API com a sessao (nunca ha URL publica). Clicar amplia. */
export function RequestPhotos({ schoolId, requestId, photos }: Props) {
  if (photos.length === 0) return <p className="mt-1 text-sub text-ink-2">Nenhuma foto anexada.</p>;
  return (
    <ul aria-label="Fotos da solicitação" className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
      {photos.map((photo, index) => (
        <Photo key={photo.id} schoolId={schoolId} requestId={requestId} photo={photo} index={index} />
      ))}
    </ul>
  );
}
