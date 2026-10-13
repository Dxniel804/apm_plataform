import { describe, expect, it, vi } from "vitest";
import { json, problem } from "@/test-utils/auth-fixtures";
import { photoBody, requestDetailBody, requestSummaryBody, REQUEST_ID } from "@/test-utils/request-fixtures";
import { SCHOOL_ID } from "@/test-utils/statement-fixtures";
import {
  cancelStaffRequest, createStaffRequest, downloadRequestPhoto, getStaffRequest, listStaffRequests, resolveStaffRequest, startStaffRequest,
  uploadRequestPhoto,
} from "./staff-requests";

const ok = (body: unknown, status = 200) => vi.fn().mockResolvedValue(json(body, status, { "Content-Type": "application/json" }));
const csrf = "c".repeat(32);
type Init = RequestInit & { headers: Record<string, string> };
const init = (f: ReturnType<typeof vi.fn>): Init => f.mock.calls[0]![1] as Init;
const url = (f: ReturnType<typeof vi.fn>) => f.mock.calls[0]![0] as string;

describe("leitura", () => {
  it("lista com filtros (situacao, categoria, mes, cursor, limite) em camelCase", async () => {
    const f = ok({ items: [requestSummaryBody()], next_cursor: "c2" });
    const result = await listStaffRequests(SCHOOL_ID, { status: "OPEN", category: "SUPPLIES", period: "2026-10", cursor: "x", limit: 50 }, { fetchImpl: f });
    expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests?status=OPEN&category=SUPPLIES&period=2026-10&cursor=x&limit=50`);
    expect(result).toMatchObject({
      ok: true,
      data: { nextCursor: "c2", items: [{ id: REQUEST_ID, category: "SUPPLIES", status: "OPEN", attachmentsCount: 1, resolvedAt: null, authorUserId: expect.any(String) }] },
    });
  });

  it("sem filtros: so o caminho", async () => {
    const f = ok({ items: [], next_cursor: null });
    await listStaffRequests(SCHOOL_ID, {}, { fetchImpl: f });
    expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests`);
  });

  it("detalhe: fotos, nota da gestao e quem fez o que", async () => {
    const f = ok(requestDetailBody({ status: "RESOLVED", resolution_note: "Comprado.", resolved_at: "2026-10-07T10:00:00Z", resolved_by_user_id: "u2", started_at: "2026-10-06T15:00:00Z", started_by_user_id: "u2" }));
    const result = await getStaffRequest(SCHOOL_ID, REQUEST_ID, { fetchImpl: f });
    expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests/${REQUEST_ID}`);
    expect(result).toMatchObject({
      ok: true,
      data: { status: "RESOLVED", resolutionNote: "Comprado.", resolvedByUserId: "u2", startedByUserId: "u2", photos: [{ fileName: "foto.jpg", sizeBytes: 20480 }] },
    });
  });

  it("recusa situacao, categoria, contagem ou foto mal formadas (nada de adivinhar)", async () => {
    for (const bad of [
      requestSummaryBody({ status: "DONE" }), requestSummaryBody({ category: "NOPE" }), requestSummaryBody({ attachments_count: 1.5 }),
      requestSummaryBody({ title: "" }), requestSummaryBody({ author_user_id: null }),
    ]) {
      expect((await listStaffRequests(SCHOOL_ID, {}, { fetchImpl: ok({ items: [bad], next_cursor: null }) })).ok).toBe(false);
    }
    expect((await getStaffRequest(SCHOOL_ID, REQUEST_ID, { fetchImpl: ok(requestDetailBody({ attachments: [photoBody({ size_bytes: "x" })] })) })).ok).toBe(false);
    expect((await getStaffRequest(SCHOOL_ID, REQUEST_ID, { fetchImpl: ok(requestDetailBody({ attachments: undefined })) })).ok).toBe(false);
    expect((await listStaffRequests(SCHOOL_ID, {}, { fetchImpl: ok({ items: [], next_cursor: 5 }) })).ok).toBe(false);
  });

  it("403 e 404 viram erros com code", async () => {
    expect(await getStaffRequest(SCHOOL_ID, REQUEST_ID, { fetchImpl: vi.fn().mockResolvedValue(problem("not_found", 404)) })).toMatchObject({ error: { status: 404, code: "not_found" } });
    expect(await listStaffRequests(SCHOOL_ID, {}, { fetchImpl: vi.fn().mockResolvedValue(problem("permission_denied", 403)) })).toMatchObject({ error: { status: 403 } });
  });
});

describe("escrita", () => {
  it("abrir: POST com categoria e titulo, descricao so quando existe, sem nome de pessoa", async () => {
    const f = ok(requestDetailBody(), 201);
    const result = await createStaffRequest(SCHOOL_ID, { category: "MAINTENANCE", title: "Torneira", description: "" }, { fetchImpl: f, csrfToken: csrf });
    expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests`);
    expect(init(f).method).toBe("POST");
    expect(init(f).headers["X-CSRF-Token"]).toBe(csrf);
    expect(JSON.parse(init(f).body as string)).toEqual({ category: "MAINTENANCE", title: "Torneira" });
    expect(result.ok).toBe(true);

    const g = ok(requestDetailBody(), 201);
    await createStaffRequest(SCHOOL_ID, { category: "EVENT", title: "Festa", description: "Junina" }, { fetchImpl: g, csrfToken: csrf });
    expect(JSON.parse(init(g).body as string)).toEqual({ category: "EVENT", title: "Festa", description: "Junina" });
  });

  it("foto: multipart so com `file`; sem Content-Type manual (o navegador poe o boundary); conteudo so no corpo", async () => {
    const f = ok(photoBody(), 201);
    const file = new File(["\x89PNG conteudo secreto"], "foto.png", { type: "image/png" });
    const result = await uploadRequestPhoto(SCHOOL_ID, REQUEST_ID, file, { fetchImpl: f, csrfToken: csrf });
    expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests/${REQUEST_ID}/attachments`);
    expect(url(f)).not.toContain("foto");
    const i = init(f);
    expect(i.method).toBe("POST");
    expect(i.body).toBeInstanceOf(FormData);
    expect(((i.body as FormData).get("file") as File).name).toBe("foto.png");
    expect([...(i.body as FormData).keys()]).toEqual(["file"]);
    expect(i.headers["Content-Type"]).toBeUndefined();
    expect(i.headers["X-CSRF-Token"]).toBe(csrf);
    expect(result).toMatchObject({ ok: true, data: { fileName: "foto.jpg" } });
  });

  it("foto: 409, 413 e 415 viram erros", async () => {
    const file = new File(["x"], "f.png");
    for (const [code, status] of [["attachments_closed", 409], ["payload_too_large", 413], ["attachment_type_not_allowed", 415]] as const) {
      const r = await uploadRequestPhoto(SCHOOL_ID, REQUEST_ID, file, { fetchImpl: vi.fn().mockResolvedValue(problem(code, status)) });
      expect(r).toMatchObject({ ok: false, error: { status, code } });
    }
  });

  it("baixar foto: GET pela API; devolve o Blob e o tipo", async () => {
    const f = vi.fn().mockResolvedValue(new Response("JPEGDATA", { status: 200, headers: { "Content-Type": "image/jpeg" } }));
    const result = await downloadRequestPhoto(SCHOOL_ID, REQUEST_ID, "p1", { fetchImpl: f });
    expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests/${REQUEST_ID}/attachments/p1`);
    expect(result.ok && result.data.contentType).toBe("image/jpeg");
    expect(await downloadRequestPhoto(SCHOOL_ID, REQUEST_ID, "p1", { fetchImpl: vi.fn().mockResolvedValue(problem("not_found", 404)) })).toMatchObject({ ok: false, error: { code: "not_found" } });
  });

  it("acoes: iniciar e cancelar sem corpo; resolver com a nota so quando existe", async () => {
    for (const [fn, name] of [[startStaffRequest, "start"], [cancelStaffRequest, "cancel"]] as const) {
      const f = ok(requestDetailBody());
      await fn(SCHOOL_ID, REQUEST_ID, { fetchImpl: f, csrfToken: csrf });
      expect(url(f)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests/${REQUEST_ID}/${name}`);
      expect(init(f).method).toBe("POST");
      expect(init(f).body).toBeUndefined();
    }
    const withNote = ok(requestDetailBody({ status: "RESOLVED" }));
    await resolveStaffRequest(SCHOOL_ID, REQUEST_ID, "Comprado.", { fetchImpl: withNote, csrfToken: csrf });
    expect(url(withNote)).toBe(`/api/v1/schools/${SCHOOL_ID}/requests/${REQUEST_ID}/resolve`);
    expect(JSON.parse(init(withNote).body as string)).toEqual({ note: "Comprado." });
    const without = ok(requestDetailBody({ status: "RESOLVED" }));
    await resolveStaffRequest(SCHOOL_ID, REQUEST_ID, undefined, { fetchImpl: without, csrfToken: csrf });
    expect(init(without).body).toBeUndefined();
  });

  it("uma resposta que nao e um pedido valido nao vira sucesso", async () => {
    const r = await startStaffRequest(SCHOOL_ID, REQUEST_ID, { fetchImpl: ok({ status: "WHATEVER" }), csrfToken: csrf });
    expect(r.ok).toBe(false);
  });
});
