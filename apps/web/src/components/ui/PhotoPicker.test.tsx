import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PhotoPicker } from "./PhotoPicker";

const png = (name = "foto.png", size = 1000) => new File([new Uint8Array(size)], name, { type: "image/png" });

function Harness({ max, initial = [] as File[], onChange = () => {} }: { max?: number; initial?: File[]; onChange?: (photos: File[]) => void }) {
  const [photos, setPhotos] = useState<File[]>(initial);
  return (
    <PhotoPicker
      photos={photos}
      max={max}
      onChange={(next) => {
        setPhotos(next);
        onChange(next);
      }}
    />
  );
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
});

describe("PhotoPicker: galeria", () => {
  it("escolher da galeria acrescenta fotos com previa, tamanho e botao de remover", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("Escolher fotos da galeria"), [png("a.png", 2048), png("b.png", 4096)]);

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const list = screen.getByRole("list", { name: "Fotos escolhidas" });
    expect(within(list).getByAltText("Foto 1")).toHaveAttribute("src", "blob:preview");
    expect(within(list).getByAltText("Foto 2")).toBeInTheDocument();
    expect(within(list).getByText("2 KB")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remover foto 1" }));
    expect(within(screen.getByRole("list", { name: "Fotos escolhidas" })).getAllByRole("img")).toHaveLength(1);
  });

  it("recusa o que nao e foto (PDF, SVG), diz o motivo e nao acrescenta nada", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const input = screen.getByLabelText("Escolher fotos da galeria");

    // userEvent filtra pelo `accept`; fireEvent entrega o arquivo como um navegador que ignorou o filtro
    const pdf = new File(["%PDF"], "nota.pdf", { type: "application/pdf" });
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [pdf] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("“nota.pdf” não é uma foto PNG, JPEG ou WebP.");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("list", { name: "Fotos escolhidas" })).not.toBeInTheDocument();
  });

  it("respeita o maximo: o excesso e recusado com aviso e os botoes se desligam quando enche", async () => {
    render(<Harness max={2} />);
    const user = userEvent.setup();

    await user.upload(screen.getByLabelText("Escolher fotos da galeria"), [png("a.png"), png("b.png"), png("c.png")]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Cabem no máximo 2 fotos.");
    expect(within(screen.getByRole("list", { name: "Fotos escolhidas" })).getAllByRole("img")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Escolher da galeria" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Tirar foto" })).toBeDisabled();
  });

  it("uma foto acima de 10 MB e recusada", async () => {
    render(<Harness />);
    const huge = png("enorme.png", 10 * 1024 * 1024 + 1);

    await userEvent.setup().upload(screen.getByLabelText("Escolher fotos da galeria"), huge);

    expect(await screen.findByRole("alert")).toHaveTextContent("“enorme.png” é grande demais");
  });
});

describe("PhotoPicker: camera", () => {
  function stubCamera() {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { configurable: true, get: () => 4000 });
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { configurable: true, get: () => 3000 });
    const draw = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: draw } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["jpeg"], { type: "image/jpeg" })));
    return { stop, getUserMedia, draw };
  }

  it("Tirar foto abre a camera traseira, captura em JPEG com o lado maior limitado e para o video", async () => {
    const { stop, getUserMedia, draw } = stubCamera();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Tirar foto" }));
    const dialog = await screen.findByRole("dialog", { name: "Tirar foto com a câmera" });
    expect(getUserMedia).toHaveBeenCalledWith({ video: { facingMode: { ideal: "environment" } }, audio: false });
    const shoot = within(dialog).getByRole("button", { name: "Tirar a foto" });
    await waitFor(() => expect(shoot).toBeEnabled());

    await user.click(shoot);

    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    const [photo] = onChange.mock.calls[0]![0] as File[];
    expect(photo!.type).toBe("image/jpeg");
    expect(photo!.name).toMatch(/^foto-\d+\.jpg$/);
    expect(draw).toHaveBeenCalledWith(expect.anything(), 0, 0, 2400, 1800); // 4000x3000 reduzido
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(stop).toHaveBeenCalled(); // a camera nao fica ligada
    expect(screen.getByAltText("Foto 1")).toBeInTheDocument();
  });

  it("Cancelar fecha a janela e desliga a camera sem acrescentar foto", async () => {
    const { stop } = stubCamera();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Tirar foto" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Tirar a foto" })).toBeEnabled());
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(stop).toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it.each([
    ["NotAllowedError", "bloqueada"],
    ["NotFoundError", "Não encontramos uma câmera"],
    ["NotReadableError", "em uso por outro aplicativo"],
    ["AbortError", "Não foi possível abrir a câmera"],
  ])("camera que nao abre (%s) explica o motivo e oferece a galeria", async (name, text) => {
    const error = Object.assign(new Error(name), { name });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(error) } });
    render(<Harness />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Tirar foto" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(text);
    expect(alert).toHaveTextContent("galeria");
    expect(screen.queryByRole("button", { name: "Tirar a foto" })).not.toBeInTheDocument();
  });

  it("sem getUserMedia (navegador antigo) usa a camera do sistema pelo campo com capture", async () => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
    render(<Harness />);
    const system = screen.getByLabelText("Tirar foto com a câmera do aparelho");
    expect(system).toHaveAttribute("capture", "environment");
    const click = vi.spyOn(system, "click");

    await userEvent.setup().click(screen.getByRole("button", { name: "Tirar foto" }));

    expect(click).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
