import { describe, expect, it, vi } from "vitest";
import { fitPhoto, isPhotoFile, type PhotoEnv } from "./photo";

const photo = (size: number, name = "IMG_0001.png", type = "image/png") => new File([new Uint8Array(size)], name, { type });

function env(width: number, height: number, encoded: number | null): PhotoEnv & { close: ReturnType<typeof vi.fn> } {
  const close = vi.fn();
  return {
    close,
    decode: async () => ({ width, height, close }),
    encode: vi.fn(async () => (encoded === null ? null : new Blob([new Uint8Array(encoded)], { type: "image/jpeg" }))),
  };
}

describe("fitPhoto", () => {
  it("foto pequena e leve segue como esta", async () => {
    const original = photo(200_000);
    const e = env(1200, 900, 1);
    expect(await fitPhoto(original, {}, e)).toBe(original);
    expect(e.encode).not.toHaveBeenCalled();
    expect(e.close).toHaveBeenCalled();
  });

  it("foto grande em pixels e reduzida (lado maior 2400) e regravada em JPEG", async () => {
    const original = photo(6_000_000);
    const e = env(4000, 3000, 900_000);
    const fitted = await fitPhoto(original, {}, e);
    expect(e.encode).toHaveBeenCalledWith(expect.anything(), 2400, 1800, 0.85);
    expect(fitted).not.toBe(original);
    expect(fitted.type).toBe("image/jpeg");
    expect(fitted.name).toBe("IMG_0001.jpg");
    expect(fitted.size).toBe(900_000);
  });

  it("foto pesada mas pequena em pixels e regravada sem mudar o tamanho", async () => {
    const e = env(2000, 1500, 700_000);
    await fitPhoto(photo(4_000_000), {}, e);
    expect(e.encode).toHaveBeenCalledWith(expect.anything(), 2000, 1500, 0.85);
  });

  it("se regravar nao ajudou, ou falhou, fica a original", async () => {
    const big = photo(3_000_000);
    expect(await fitPhoto(big, {}, env(4000, 3000, 3_500_000))).toBe(big); // maior que a original
    expect(await fitPhoto(big, {}, env(4000, 3000, null))).toBe(big); // sem blob
    expect(await fitPhoto(big, {}, env(4000, 3000, 0))).toBe(big); // vazio
    const broken: PhotoEnv = { decode: async () => { throw new Error("nao decodifica"); }, encode: async () => null };
    expect(await fitPhoto(big, {}, broken)).toBe(big);
  });

  it("sem os recursos do navegador devolve a original", async () => {
    const original = photo(5_000_000);
    expect(await fitPhoto(original, {}, null)).toBe(original);
    expect(await fitPhoto(original)).toBe(original); // jsdom nao tem createImageBitmap
  });

  it("aceita os limites por parametro", async () => {
    const e = env(1000, 500, 100);
    await fitPhoto(photo(100), { maxSide: 400, quality: 0.5 }, e);
    expect(e.encode).toHaveBeenCalledWith(expect.anything(), 400, 200, 0.5);
  });
});

describe("isPhotoFile", () => {
  it("PNG, JPEG e WebP; tipo vazio vale pela extensao; o resto nao", () => {
    expect(isPhotoFile(photo(1, "a.png", "image/png"))).toBe(true);
    expect(isPhotoFile(photo(1, "a.jpg", "image/jpeg"))).toBe(true);
    expect(isPhotoFile(photo(1, "a.webp", "image/webp"))).toBe(true);
    expect(isPhotoFile(photo(1, "FOTO.JPEG", ""))).toBe(true);
    expect(isPhotoFile(photo(1, "a.pdf", "application/pdf"))).toBe(false);
    expect(isPhotoFile(photo(1, "a.svg", "image/svg+xml"))).toBe(false);
    expect(isPhotoFile(photo(1, "a.heic", "image/heic"))).toBe(false);
    expect(isPhotoFile(photo(1, "a.exe", ""))).toBe(false);
  });
});
