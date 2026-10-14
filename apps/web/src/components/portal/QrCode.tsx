import { create } from "qrcode";

const QUIET = 4; // faixa branca de 4 modulos ao redor (minimo da norma)

/** Os modulos escuros do QR Code como um unico caminho SVG (a faixa branca de 4 modulos esta incluida no `total`). */
export function qrShape(payload: string): { total: number; path: string } | null {
  try {
    const { modules } = create(payload, { errorCorrectionLevel: "M" });
    const size = modules.size;
    const parts: string[] = [];
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        if (modules.get(y, x)) parts.push(`M${x + QUIET} ${y + QUIET}h1v1h-1z`);
      }
    }
    return { total: size + QUIET * 2, path: parts.join("") };
  } catch {
    return null;
  }
}

/** O QR Code como um arquivo SVG completo (fundo branco), para baixar e imprimir. */
export function qrSvgFile(payload: string): string | null {
  const shape = qrShape(payload);
  if (!shape) return null;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${shape.total} ${shape.total}" width="1024" height="1024" shape-rendering="crispEdges"><rect width="${shape.total}" height="${shape.total}" fill="#ffffff"/><path d="${shape.path}" fill="#101a3f"/></svg>`;
}

/**
 * Desenha o QR Code no proprio navegador (e no servidor) a partir do texto do Pix. Sem chamada
 * externa e sem innerHTML: so um <path> SVG com os modulos escuros. O texto nunca sai da pagina.
 */
export function QrCode({ payload, compact = false, label }: { payload: string; compact?: boolean; label?: string }) {
  const shape = qrShape(payload);
  if (!shape) {
    return (
      <p role="alert" className="mx-auto max-w-[34ch] text-center text-sub text-ink-2">
        Não foi possível desenhar o QR Code. {label ? "Copie o endereço ao lado." : "Use o código copia e cola abaixo."}
      </p>
    );
  }
  const { total, path } = shape;
  return (
    <div className={`aspect-square w-full rounded-[var(--r-md)] bg-white p-2 shadow-[0_0_0_1px_var(--line)] ${compact ? "mx-auto max-w-[17rem] sm:mx-0 sm:max-w-[11rem] sm:shrink-0" : "mx-auto max-w-[17rem]"}`}>
      <svg
        viewBox={`0 0 ${total} ${total}`}
        className="size-full"
        role="img"
        aria-label={label ?? "QR Code do Pix. Aponte a câmera do app do seu banco para pagar."}
        shapeRendering="crispEdges"
      >
        <path d={path} fill="#101a3f" />
      </svg>
    </div>
  );
}
