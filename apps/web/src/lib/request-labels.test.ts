import { describe, expect, it } from "vitest";
import type { ApiError } from "@/lib/api/types";
import { CATEGORY_LABELS, CATEGORY_ORDER, describeRequestError, requestStatusView } from "./request-labels";

const problem = (code: string, status: number, extra: Partial<ApiError> = {}): ApiError => ({ kind: "problem", status, code, ...extra }) as ApiError;

describe("textos das solicitacoes", () => {
  it("toda categoria e toda situacao tem texto em portugues", () => {
    expect(CATEGORY_ORDER.map((c) => CATEGORY_LABELS[c])).toEqual(["Compra de material", "Manutenção", "Evento", "Financeiro", "Outros"]);
    expect(requestStatusView("OPEN")).toEqual({ label: "Aberta", tone: "info" });
    expect(requestStatusView("IN_PROGRESS")).toEqual({ label: "Em andamento", tone: "warning" });
    expect(requestStatusView("RESOLVED")).toEqual({ label: "Resolvida", tone: "success" });
    expect(requestStatusView("CANCELLED")).toEqual({ label: "Cancelada", tone: "neutral" });
  });

  it("cada code da API vira um texto proprio, nunca o do servidor", () => {
    for (const [code, status, text] of [
      ["author_only", 403, "Só quem abriu"],
      ["permission_denied", 403, "não tem permissão"],
      ["not_found", 404, "Não encontramos"],
      ["invalid_state", 409, "mudou de situação"],
      ["attachments_closed", 409, "enquanto ela está aberta"],
      ["attachment_limit", 409, "máximo de 6 fotos"],
      ["attachment_duplicate", 409, "já foi anexada"],
      ["attachment_type_not_allowed", 415, "PNG, JPEG ou WebP"],
      ["payload_too_large", 413, "10 MB"],
      ["state_conflict", 409, "Atualize a lista"],
      ["csrf_failed", 403, "Recarregue a página"],
    ] as const) {
      expect(describeRequestError(problem(code, status)).general).toContain(text);
    }
  });

  it("erro de campo vira o texto do campo; sem campo conhecido, um aviso geral", () => {
    const fields = describeRequestError(problem("validation_error", 422, { fields: [{ field: "title", code: "invalid" }, { field: "weird", code: "x" }] }));
    expect(fields.general).toBeNull();
    expect(fields.fields).toEqual({ title: "O título precisa ter de 1 a 120 caracteres.", weird: "Confira este campo." });
    expect(describeRequestError(problem("validation_error", 422)).general).toContain("Confira os dados");
  });

  it("rede, tempo, 411/413 e codigo desconhecido nao viram sucesso nem mostram texto do servidor", () => {
    expect(describeRequestError({ kind: "network" } as ApiError).general).toContain("Nada foi alterado");
    expect(describeRequestError({ kind: "timeout" } as ApiError).general).toContain("Nada foi alterado");
    expect(describeRequestError({ kind: "http", status: 413 } as ApiError).general).toContain("10 MB");
    expect(describeRequestError(problem("weird_code", 500)).general).toContain("Algo deu errado");
    expect(describeRequestError(problem("weird_code", 409)).general).toContain("Outra pessoa");
    expect(describeRequestError(problem("rate_limited", 429, { retryAfterSeconds: 30 }) as ApiError).general).toContain("Aguarde");
  });
});
