import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { ApiResult, StaffRequestDetail } from "@/lib/api/types";
import { REQUEST_AUTHOR_ID, REQUEST_ID, REQUEST_MANAGER_ID, requestDetail, requestPhoto } from "@/test-utils/request-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import { RequestDetailPanel } from "./RequestDetailPanel";

const STAFF = ["requests:read_own", "requests:submit"];
const MANAGER = ["requests:read_all", "requests:manage"];
const ADMIN = [...STAFF, ...MANAGER];

const ok = (data: StaffRequestDetail): ApiResult<StaffRequestDetail> => ({ ok: true, data });

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:foto");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(api.requests, "download").mockResolvedValue({ ok: true, data: { blob: new Blob(["jpeg"], { type: "image/jpeg" }), contentType: "image/jpeg" } as never });
});
afterEach(() => vi.restoreAllMocks());

function open(detail: StaffRequestDetail, userId: string, permissions: string[], onChanged = vi.fn()) {
  vi.spyOn(api.requests, "get").mockResolvedValue(ok(detail));
  render(<RequestDetailPanel schoolId={SCHOOL_ID} requestId={REQUEST_ID} userId={userId} permissions={permissions} onChanged={onChanged} />);
  return { onChanged, user: userEvent.setup() };
}

describe("detalhe da solicitacao", () => {
  it("mostra situacao, categoria, descricao, a resposta da gestao e as fotos baixadas pela API", async () => {
    open(requestDetail({ status: "RESOLVED", resolvedAt: "2026-10-07T10:00:00Z", resolutionNote: "Comprado, chega na segunda." }), REQUEST_AUTHOR_ID, STAFF);

    expect(await screen.findByText("Resolvida")).toBeInTheDocument();
    expect(screen.getByText("Compra de material")).toBeInTheDocument();
    expect(screen.getByText("Acabou no banheiro do segundo andar.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Resposta da gestão: Comprado, chega na segunda.");
    expect(await screen.findByAltText("Foto 1")).toHaveAttribute("src", "blob:foto");
    expect(api.requests.download).toHaveBeenCalledWith(SCHOOL_ID, REQUEST_ID, requestPhoto().id);
    // resolvida: ninguem anexa nem cancela mais
    expect(screen.queryByRole("button", { name: "Cancelar solicitação" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Escolher fotos da galeria")).not.toBeInTheDocument();
  });

  it("clicar na foto abre a ampliada, com Baixar e Fechar", async () => {
    const { user } = open(requestDetail(), REQUEST_AUTHOR_ID, STAFF);

    await user.click(await screen.findByRole("button", { name: "Ver foto 1 em tamanho maior" }));

    const dialog = await screen.findByRole("dialog", { name: "Foto 1" });
    expect(dialog).toHaveTextContent("foto.jpg · 20 KB");
    await user.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("foto que a API nao entrega aparece como indisponivel, sem derrubar a tela", async () => {
    vi.spyOn(api.requests, "download").mockResolvedValue({ ok: false, error: { kind: "problem", status: 500, code: "attachment_unavailable" } });
    open(requestDetail(), REQUEST_AUTHOR_ID, STAFF);

    expect(await screen.findByText("Foto indisponível")).toBeInTheDocument();
  });

  it("autor com pedido aberto: anexa mais fotos e cancela; nao ve as acoes da gestao", async () => {
    open(requestDetail({ photos: [requestPhoto()] }), REQUEST_AUTHOR_ID, STAFF);

    expect(await screen.findByRole("button", { name: "Cancelar solicitação" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tirar foto" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Iniciar atendimento" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Marcar como resolvida" })).not.toBeInTheDocument();
  });

  it("anexar mais fotos: envia pela API e recarrega o pedido", async () => {
    const upload = vi.spyOn(api.requests, "upload").mockResolvedValue({ ok: true, data: requestPhoto({ id: "novo" }) });
    const { onChanged, user } = open(requestDetail(), REQUEST_AUTHOR_ID, STAFF);
    await screen.findByRole("button", { name: "Tirar foto" });

    await user.upload(screen.getByLabelText("Escolher fotos da galeria"), new File([new Uint8Array(100)], "nova.png", { type: "image/png" }));
    await user.click(await screen.findByRole("button", { name: "Enviar a foto" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Fotos anexadas."));
    expect(upload).toHaveBeenCalledWith(SCHOOL_ID, REQUEST_ID, expect.objectContaining({ name: "nova.png" }));
  });

  it("autor cancela pela API e a lista e avisada", async () => {
    const cancel = vi.spyOn(api.requests, "cancel").mockResolvedValue(ok(requestDetail({ status: "CANCELLED" })));
    const { onChanged, user } = open(requestDetail(), REQUEST_AUTHOR_ID, STAFF);

    await user.click(await screen.findByRole("button", { name: "Cancelar solicitação" }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Solicitação cancelada."));
    expect(cancel).toHaveBeenCalledWith(SCHOOL_ID, REQUEST_ID);
    expect(await screen.findByText("Cancelada")).toBeInTheDocument();
  });

  it("gestao: inicia o atendimento e depois resolve com uma nota", async () => {
    const start = vi.spyOn(api.requests, "start").mockResolvedValue(ok(requestDetail({ status: "IN_PROGRESS", startedAt: "2026-10-06T15:00:00Z", startedByUserId: REQUEST_MANAGER_ID })));
    const resolve = vi.spyOn(api.requests, "resolve").mockResolvedValue(ok(requestDetail({ status: "RESOLVED", resolvedAt: "2026-10-07T10:00:00Z", resolutionNote: "Feito." })));
    const { onChanged, user } = open(requestDetail(), REQUEST_MANAGER_ID, MANAGER);

    expect(screen.queryByRole("button", { name: "Cancelar solicitação" })).not.toBeInTheDocument(); // nao e dele
    await user.click(await screen.findByRole("button", { name: "Iniciar atendimento" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Atendimento iniciado."));
    expect(start).toHaveBeenCalledWith(SCHOOL_ID, REQUEST_ID);
    expect(await screen.findByText("Em andamento")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Iniciar atendimento" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Marcar como resolvida" }));
    await user.type(screen.getByLabelText(/Resposta para quem pediu/), "  Feito.  ");
    await user.click(screen.getAllByRole("button", { name: "Marcar como resolvida" }).at(-1)!);

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Solicitação resolvida."));
    expect(resolve).toHaveBeenCalledWith(SCHOOL_ID, REQUEST_ID, "Feito.");
    expect(await screen.findByText("Resolvida")).toBeInTheDocument();
  });

  it("resolver sem nota manda sem nota", async () => {
    const resolve = vi.spyOn(api.requests, "resolve").mockResolvedValue(ok(requestDetail({ status: "RESOLVED", resolvedAt: "2026-10-07T10:00:00Z" })));
    const { user } = open(requestDetail(), REQUEST_MANAGER_ID, MANAGER);

    await user.click(await screen.findByRole("button", { name: "Marcar como resolvida" }));
    await user.click(screen.getAllByRole("button", { name: "Marcar como resolvida" }).at(-1)!);

    await waitFor(() => expect(resolve).toHaveBeenCalledWith(SCHOOL_ID, REQUEST_ID, undefined));
  });

  it("administrador (as duas funcoes): ve as acoes de autor e de gestao em um pedido proprio", async () => {
    open(requestDetail(), REQUEST_AUTHOR_ID, ADMIN);

    expect(await screen.findByRole("button", { name: "Iniciar atendimento" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marcar como resolvida" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar solicitação" })).toBeInTheDocument();
  });

  it("409: a tela recarrega do servidor e mostra o aviso em portugues", async () => {
    const get = vi.spyOn(api.requests, "get").mockResolvedValue(ok(requestDetail()));
    vi.spyOn(api.requests, "start").mockResolvedValue({ ok: false, error: { kind: "problem", status: 409, code: "invalid_state" } });
    render(<RequestDetailPanel schoolId={SCHOOL_ID} requestId={REQUEST_ID} userId={REQUEST_MANAGER_ID} permissions={MANAGER} onChanged={vi.fn()} />);

    await userEvent.setup().click(await screen.findByRole("button", { name: "Iniciar atendimento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("mudou de situação");
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("pedido que nao existe ou sem acesso: aviso, nao tela quebrada", async () => {
    vi.spyOn(api.requests, "get").mockResolvedValue({ ok: false, error: { kind: "problem", status: 404, code: "not_found" } });
    render(<RequestDetailPanel schoolId={SCHOOL_ID} requestId={REQUEST_ID} userId={REQUEST_AUTHOR_ID} permissions={STAFF} onChanged={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Não encontramos esta solicitação");
  });
});
