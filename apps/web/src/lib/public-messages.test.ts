import { describe, expect, it } from "vitest";
import type { ApiError } from "@/lib/api/types";
import { describeContributionError, describeOrderError, describeRenewError } from "./public-messages";

const problem = (code: string, status: number, extra: Partial<ApiError> = {}): ApiError => ({ kind: "problem", status, code, ...extra });

describe("describeContributionError", () => {
  it("422: erros por campo, em portugues, ao lado do campo certo", () => {
    const out = describeContributionError(
      problem("validation_error", 422, {
        fields: [
          { field: "amount_cents", code: "out_of_range" },
          { field: "contributor_email", code: "invalid" },
          { field: "guardian_name", code: "required" },
          { field: "contributor_phone", code: "invalid" },
        ],
      }),
    );
    expect(out.amount).toBe("O valor não está dentro do que a escola aceita.");
    expect(out.fields).toEqual({
      contributorEmail: "Confira este campo.",
      guardianName: "Informe o nome do responsável.",
      contributorPhone: "Confira este campo.",
    });
    expect(out.general).toBeNull();
  });

  it("valor fora da lista sugerida e 422 sem campos conhecidos", () => {
    expect(describeContributionError(problem("validation_error", 422, { fields: [{ field: "amount_cents", code: "not_suggested" }] })).amount).toMatch(/só os valores sugeridos/);
    expect(describeContributionError(problem("validation_error", 422)).general).toMatch(/Algum dado não foi aceito/);
    expect(describeContributionError(problem("validation_error", 422, { fields: [{ field: "Idempotency-Key", code: "required" }] })).general).toMatch(/Recarregue/);
  });

  it("429 com tempo, rede, 501, 409 e erro generico", () => {
    expect(describeContributionError(problem("rate_limited", 429, { retryAfterSeconds: 90 })).general).toContain("2 minutos");
    expect(describeContributionError({ kind: "network" }).general).toMatch(/Nada foi cobrado/);
    expect(describeContributionError({ kind: "http", status: 501 }).general).toMatch(/ainda não está disponível/);
    expect(describeContributionError(problem("idempotency_key_reused", 409)).general).toMatch(/Confira os dados/);
    expect(describeContributionError(problem("internal_error", 500)).general).toMatch(/Tente de novo/);
    expect(describeContributionError(problem("not_found", 404)).general).toMatch(/Não encontramos esta escola/);
  });

  it("nunca repassa texto do servidor", () => {
    const hostile = { kind: "problem", status: 500, code: "internal_error", title: "Internal Server Error" } as ApiError;
    expect(JSON.stringify(describeContributionError(hostile))).not.toMatch(/Internal/);
  });
});

describe("describeRenewError", () => {
  it("contribuicao fechada, 429, rede e generico", () => {
    expect(describeRenewError(problem("contribution_closed", 409))).toMatch(/não está mais aguardando pagamento/);
    expect(describeRenewError(problem("rate_limited", 429, { retryAfterSeconds: 30 }))).toContain("30 segundos");
    expect(describeRenewError({ kind: "timeout" })).toMatch(/conexão/);
    expect(describeRenewError(problem("internal_error", 500))).toMatch(/novo QR/);
  });
});

describe("describeOrderError", () => {
  const problem = (code: string, status: number, extra: Partial<ApiError> = {}): ApiError => ({ kind: "problem", status, code, ...extra });

  it("rede: nada foi cobrado", () => {
    expect(describeOrderError({ kind: "network" }).general).toContain("Nada foi cobrado");
  });

  it("o servidor recusa produtos: o aviso vai para a linha certa e nao para o geral", () => {
    const out = describeOrderError(problem("validation_error", 422, { fields: [{ field: "lines[0].quantity", code: "over_limit" }, { field: "lines[2].item_id", code: "unavailable" }, { field: "lines[1].item_id", code: "duplicate" }] }));
    expect(out.general).toBeNull();
    expect(out.lines[0]).toContain("limite por pedido");
    expect(out.lines[1]).toContain("duas vezes");
    expect(out.lines[2]).toContain("não está mais à venda");
  });

  it("total acima do limite e campo de identificacao recusado", () => {
    expect(describeOrderError(problem("validation_error", 422, { fields: [{ field: "lines", code: "total_out_of_range" }] })).general).toContain("R$ 50.000,00");
    const out = describeOrderError(problem("validation_error", 422, { fields: [{ field: "guardian_name", code: "required" }, { field: "contributor_email", code: "invalid" }] }));
    expect(out.fields.guardianName).toBeTruthy();
    expect(out.fields.contributorEmail).toBe("Confira este campo.");
  });

  it("campanha fora do ar, mudou, chave reusada, sem Pix e limite de tentativas", () => {
    expect(describeOrderError(problem("not_found", 404)).general).toContain("não está mais à venda");
    expect(describeOrderError(problem("campaign_changed", 409)).general).toContain("mudou enquanto você montava");
    expect(describeOrderError(problem("idempotency_key_reused", 409)).general).toContain("Confira o carrinho");
    expect(describeOrderError(problem("payment_unavailable", 409)).general).toContain("não pode receber pelo Pix");
    expect(describeOrderError(problem("rate_limited", 429, { retryAfterSeconds: 30 })).general).toContain("30");
    expect(describeOrderError({ kind: "problem", status: 501, code: "payment_not_configured" }).general).toContain("Pix");
  });

  it("nunca mostra texto do servidor e um code novo cai no texto generico", () => {
    expect(describeOrderError(problem("something_new", 500)).general).toContain("Nada foi cobrado");
    expect(describeOrderError(problem("validation_error", 422)).general).toContain("Algum dado do pedido");
  });
});
