"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { CameraIcon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";

interface CameraDialogProps {
  open: boolean;
  onClose: () => void;
  /** Recebe a foto tirada (JPEG). A janela se fecha em seguida. */
  onCapture: (photo: File) => void;
}

export function cameraErrorText(error: unknown): string {
  const name = error instanceof DOMException || (typeof error === "object" && error !== null && "name" in error) ? String((error as { name: unknown }).name) : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "A câmera está bloqueada para esta página. Libere o acesso no navegador ou escolha uma foto da galeria.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") return "Não encontramos uma câmera neste aparelho. Escolha uma foto da galeria.";
  if (name === "NotReadableError") return "A câmera está em uso por outro aplicativo. Feche-o e tente de novo, ou escolha uma foto da galeria.";
  return "Não foi possível abrir a câmera. Escolha uma foto da galeria.";
}

/** Maior lado da foto tirada: a mesma regra da galeria, para caber nos 10 MB do servidor. */
const MAX_SIDE = 2400;

function CameraView({ onClose, onCapture }: Omit<CameraDialogProps, "open">) {
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<"starting" | "ready" | "error">("starting");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let stream: MediaStream | null = null;
    const stop = () => stream?.getTracks().forEach((track) => track.stop());
    const devices = typeof navigator === "undefined" ? undefined : navigator.mediaDevices;
    if (!devices?.getUserMedia) {
      queueMicrotask(() => {
        if (cancelled) return;
        setMessage(cameraErrorText(null));
        setState("error");
      });
      return () => {
        cancelled = true;
      };
    }
    devices
      .getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
      .then((opened) => {
        if (cancelled) {
          opened.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = opened;
        const element = video.current;
        if (element) {
          element.srcObject = opened;
          void element.play().catch(() => undefined);
        }
        setState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setMessage(cameraErrorText(error));
        setState("error");
      });
    return () => {
      cancelled = true;
      stop();
    };
  }, []);

  function capture() {
    const element = video.current;
    if (!element || !element.videoWidth || !element.videoHeight) return;
    const scale = Math.min(1, MAX_SIDE / Math.max(element.videoWidth, element.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(element.videoWidth * scale);
    canvas.height = Math.round(element.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) {
      setMessage("Não foi possível tirar a foto. Escolha uma da galeria.");
      return setState("error");
    }
    context.drawImage(element, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setMessage("Não foi possível tirar a foto. Tente de novo.");
          return;
        }
        onCapture(new File([blob], `foto-${Date.now()}.jpg`, { type: "image/jpeg", lastModified: Date.now() }));
      },
      "image/jpeg",
      0.9,
    );
  }

  return (
    <div className="p-5 sm:p-7">
      <h2 className="text-heading text-brand-800">Tirar foto</h2>
      {state !== "error" && (
        <div className="relative mt-4 overflow-hidden rounded-[var(--r-lg)] bg-black">
          {/* playsInline: no iPhone o video abre na propria pagina, nao em tela cheia. */}
          <video ref={video} playsInline muted autoPlay aria-label="Imagem da câmera" className="block max-h-[60dvh] w-full object-contain" />
          {state === "starting" && (
            <p role="status" className="absolute inset-0 grid place-items-center text-sub text-white">
              Abrindo a câmera…
            </p>
          )}
        </div>
      )}
      {message && (
        <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {message}
        </p>
      )}
      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button variant="plain" size="md" onClick={onClose} className="rounded-full!">
          Cancelar
        </Button>
        {state !== "error" && (
          <Button size="md" onClick={capture} disabled={state !== "ready"} className="rounded-full!">
            <CameraIcon size={18} className="mr-2" />
            Tirar a foto
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * Camera dentro da pagina (getUserMedia): abre a camera traseira quando ha, mostra a imagem e tira a foto. O fluxo
 * de video so existe enquanto a janela esta aberta e e sempre parado ao fechar. Fica na memoria do navegador: so
 * vai para o servidor quando a pessoa envia o formulario. Exige a politica `camera=(self)` (next.config.ts).
 */
export function CameraDialog({ open, onClose, onCapture }: CameraDialogProps) {
  return (
    <Modal open={open} onClose={onClose} label="Tirar foto com a câmera">
      {open && <CameraView onClose={onClose} onCapture={onCapture} />}
    </Modal>
  );
}
