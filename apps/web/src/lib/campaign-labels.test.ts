import { describe, expect, it } from "vitest";
import type { ApiError } from "@/lib/api/types";
import { campaignStatusView, describeCampaignError, describePeriod } from "./campaign-labels";

const problem = (code: string, status: number, extra: Partial<ApiError> = {}): ApiError => ({ kind: "problem", status, code, ...extra });

describe("campaignStatusView", () => {
  it("rascunho, a venda e encerrada, em portugues e com tom proprio", () => {
    expect(campaignStatusView("DRAFT")).toEqual({ label: "Rascunho", tone: "neutral" });
    expect(campaignStatusView("ACTIVE")).toEqual({ label: "À venda", tone: "success" });
    expect(campaignStatusView("ENDED")).toEqual({ label: "Encerrada", tone: "info" });
  });
});

describe("describeCampaignError", () => {
  it("rede e tempo esgotado dizem que nada foi alterado", () => {
    expect(describeCampaignError({ kind: "network" }).general).toContain("Nada foi alterado");
    expect(describeCampaignError({ kind: "timeout" }).general).toContain("Nada foi alterado");
  });

  it("cada code conhecido tem texto proprio e nenhum texto do servidor aparece", () => {
    for (const code of ["permission_denied", "not_found", "invalid_state", "campaign_needs_a_product", "item_limit", "attachment_type_not_allowed", "payload_too_large", "csrf_failed"]) {
      const text = describeCampaignError(problem(code, 409)).general;
      expect(text, code).toBeTruthy();
      expect(text).not.toContain(code);
    }
    expect(describeCampaignError(problem("campaign_needs_a_product", 409)).general).toContain("pelo menos um produto");
    expect(describeCampaignError(problem("totally_new_code", 500)).general).toBe("Algo deu errado do nosso lado. Tente de novo em instantes.");
    expect(describeCampaignError(problem("totally_new_code", 409)).general).toContain("Atualize");
  });

  it("422 vira texto ao lado do campo; sem campo, um aviso geral", () => {
    const out = describeCampaignError(problem("validation_error", 422, { fields: [{ field: "ends_on", code: "in_the_past" }, { field: "price_cents", code: "invalid" }, { field: "file", code: "image_malformed" }, { field: "x", code: "y" }] }));
    expect(out.general).toBeNull();
    expect(out.fields.ends_on).toContain("já passou");
    expect(out.fields.price_cents).toContain("R$ 1,00 a R$ 10.000,00");
    expect(out.fields.file).toContain("corrompida");
    expect(out.fields.x).toBe("Confira este campo.");
    expect(describeCampaignError(problem("validation_error", 422)).general).toContain("Confira os dados");
  });

  it("limite de tentativas diz quanto esperar", () => {
    expect(describeCampaignError(problem("rate_limited", 429, { retryAfterSeconds: 30 })).general).toContain("30");
  });

  it("imagem grande demais (411 ou 413)", () => {
    expect(describeCampaignError({ kind: "http", status: 413 }).general).toContain("5 MB");
  });
});

describe("describePeriod", () => {
  it("diz o periodo por extenso e curto", () => {
    expect(describePeriod(null, null)).toBeNull();
    expect(describePeriod("2026-06-05", "2026-06-30")).toMatch(/^5 de jun\.? a 30 de jun/);
    expect(describePeriod(null, "2026-06-30")).toMatch(/^até 30 de jun/);
    expect(describePeriod("2026-06-05", null)).toMatch(/^a partir de 5 de jun/);
  });
});
