/**
 * Prepara uma foto para o envio: fotos de celular chegam a 5-12 MB e 4000 px, e a API aceita ate 10 MB. Reduz o
 * lado maior para `maxSide` e regrava em JPEG so quando precisa (foto pequena segue como esta). Sem os recursos do
 * navegador (ou se algo falhar), devolve a foto original: quem decide se serve e o servidor.
 */
export const PHOTO_TYPES = ["image/png", "image/jpeg", "image/webp"] as const;

export interface PhotoOptions {
  /** Lado maior, em pixels, a partir do qual a foto e reduzida. */
  maxSide?: number;
  /** Tamanho a partir do qual a foto e regravada, mesmo pequena em pixels. */
  recompressAbove?: number;
  quality?: number;
}

export interface Bitmap {
  width: number;
  height: number;
  close?: () => void;
}

export interface PhotoEnv {
  decode: (file: File) => Promise<Bitmap>;
  encode: (bitmap: Bitmap, width: number, height: number, quality: number) => Promise<Blob | null>;
}

export const browserPhotoEnv: PhotoEnv = {
  decode: (file) => createImageBitmap(file),
  encode: (bitmap, width, height, quality) =>
    new Promise((resolve) => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) return resolve(null);
      context.drawImage(bitmap as ImageBitmap, 0, 0, width, height);
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", quality);
    }),
};

function jpegName(name: string): string {
  const base = name.replace(/\.[^./\\]+$/, "") || "foto";
  return `${base}.jpg`;
}

export async function fitPhoto(file: File, options: PhotoOptions = {}, env: PhotoEnv | null = defaultEnv()): Promise<File> {
  const { maxSide = 2400, recompressAbove = 1_500_000, quality = 0.85 } = options;
  if (!env) return file;
  try {
    const bitmap = await env.decode(file);
    const longest = Math.max(bitmap.width, bitmap.height);
    if (longest <= maxSide && file.size <= recompressAbove) {
      bitmap.close?.();
      return file;
    }
    const scale = longest > maxSide ? maxSide / longest : 1;
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const blob = await env.encode(bitmap, width, height, quality);
    bitmap.close?.();
    // Se regravar nao ajudou (ou falhou), fica a original.
    if (!blob || blob.size === 0 || blob.size >= file.size) return file;
    return new File([blob], jpegName(file.name), { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return file;
  }
}

function defaultEnv(): PhotoEnv | null {
  return typeof createImageBitmap === "function" && typeof document !== "undefined" ? browserPhotoEnv : null;
}

/** O tipo vem do arquivo; alguns navegadores deixam vazio e entao vale a extensao. O servidor confere de novo pelos bytes. */
export function isPhotoFile(file: File): boolean {
  if ((PHOTO_TYPES as readonly string[]).includes(file.type)) return true;
  return file.type === "" && /\.(png|jpe?g|webp)$/i.test(file.name);
}
