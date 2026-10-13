import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { REQUEST_ID, requestDetail } from "@/test-utils/request-fixtures";
import { RequestForm } from "./RequestForm";

const png = (name = "foto.png") => new File([new Uint8Array(500)], name, { type: "image/png" });

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

function setup() {
  const onSaved = vi.fn();
  const onClose = vi.fn();
  render(<RequestForm schoolId={SCHOOL_ID} open onClose={onClose} onSaved={onSaved} />);
  return { onSaved, onClose, user: userEvent.setup() };
}

describe("Nova solicitacao", () => {
  it("pede categoria e titulo antes de falar com a API", async () => {
    const create = vi.spyOn(api.requests, "create");
    const { user } = setup();

    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    expect(screen.getByText("Escolha uma categoria.")).toBeInTheDocument();
    expect(screen.getByText("Escreva o título do pedido.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("cria o pedido (sem nome de pessoa) e envia as fotos uma a uma", async () => {
    const create = vi.spyOn(api.requests, "create").mockResolvedValue({ ok: true, data: requestDetail({ id: REQUEST_ID }) });
    const upload = vi.spyOn(api.requests, "upload").mockResolvedValue({ ok: true, data: { id: "p", fileName: "f", contentType: "image/png", sizeBytes: 1, uploadedByUserId: "u", createdAt: "x" } });
    const { onSaved, user } = setup();

    await user.selectOptions(screen.getByLabelText("Categoria"), "MAINTENANCE");
    await user.type(screen.getByLabelText("Título"), "  Torneira pingando ");
    await user.type(screen.getByLabelText(/Descrição/), "No banheiro");
    await user.upload(screen.getByLabelText("Escolher fotos da galeria"), [png("a.png"), png("b.png")]);
    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledWith(SCHOOL_ID, { category: "MAINTENANCE", title: "Torneira pingando", description: "No banheiro" });
    expect(upload).toHaveBeenCalledTimes(2);
    expect(upload).toHaveBeenNthCalledWith(1, SCHOOL_ID, REQUEST_ID, expect.objectContaining({ name: "a.png" }));
    expect(onSaved).toHaveBeenCalledWith(REQUEST_ID, "Solicitação enviada para a gestão.");
  });

  it("sem descricao nem fotos manda so categoria e titulo", async () => {
    const create = vi.spyOn(api.requests, "create").mockResolvedValue({ ok: true, data: requestDetail() });
    const upload = vi.spyOn(api.requests, "upload");
    const { onSaved, user } = setup();

    await user.selectOptions(screen.getByLabelText("Categoria"), "OTHER");
    await user.type(screen.getByLabelText("Título"), "Só isso");
    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(create).toHaveBeenCalledWith(SCHOOL_ID, { category: "OTHER", title: "Só isso", description: undefined });
    expect(upload).not.toHaveBeenCalled();
  });

  it("uma foto que o servidor recusa nao perde o pedido: avisa quantas e por que", async () => {
    vi.spyOn(api.requests, "create").mockResolvedValue({ ok: true, data: requestDetail() });
    vi.spyOn(api.requests, "upload")
      .mockResolvedValueOnce({ ok: true, data: { id: "p", fileName: "f", contentType: "image/png", sizeBytes: 1, uploadedByUserId: "u", createdAt: "x" } })
      .mockResolvedValueOnce({ ok: false, error: { kind: "problem", status: 415, code: "attachment_type_not_allowed" } });
    const { onSaved, user } = setup();

    await user.selectOptions(screen.getByLabelText("Categoria"), "EVENT");
    await user.type(screen.getByLabelText("Título"), "Festa");
    await user.upload(screen.getByLabelText("Escolher fotos da galeria"), [png("a.png"), png("b.png")]);
    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const note = onSaved.mock.calls[0]![1] as string;
    expect(note).toContain("uma foto não foi enviada");
    expect(note).toContain("PNG, JPEG ou WebP");
    expect(note).toContain("anexar de novo");
  });

  it("erro da API fica na janela, com o texto em portugues, e nada e fechado", async () => {
    vi.spyOn(api.requests, "create").mockResolvedValue({ ok: false, error: { kind: "problem", status: 422, code: "validation_error", fields: [{ field: "title", code: "invalid" }] } });
    const { onSaved, user } = setup();

    await user.selectOptions(screen.getByLabelText("Categoria"), "EVENT");
    await user.type(screen.getByLabelText("Título"), "x");
    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    expect(await screen.findByText("O título precisa ter de 1 a 120 caracteres.")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Enviar solicitação" })).toBeEnabled();
  });

  it("sessao que caiu ou rede fora: mensagem geral", async () => {
    vi.spyOn(api.requests, "create").mockResolvedValue({ ok: false, error: { kind: "network" } as never });
    const { user } = setup();

    await user.selectOptions(screen.getByLabelText("Categoria"), "EVENT");
    await user.type(screen.getByLabelText("Título"), "Festa");
    await user.click(screen.getByRole("button", { name: "Enviar solicitação" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Nada foi alterado");
  });

  it("Cancelar fecha a janela", async () => {
    const { onClose, user } = setup();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onClose).toHaveBeenCalled();
  });
});

