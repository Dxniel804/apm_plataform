import { describe, expect, it } from "vitest";
import { PDDE_OBJECTS, plain, suggestCredit, suggestObject } from "./pdde-objects";

describe("pdde-objects", () => {
  it("o texto do extrato sugere o item, e o item define capital ou custeio", () => {
    expect(suggestObject("PIX VENTILADOR DE PAREDE")).toMatchObject({ economic: "CAPITAL" });
    expect(suggestObject("PAGAMENTO SERVIÇOS REPARO PREDIAL")).toMatchObject({ label: "Pequeno reparo ou manutenção", economic: "CUSTEIO" });
    expect(suggestObject("PAGAMENTO MATERIAL ESCOLAR")).toMatchObject({ economic: "CUSTEIO" });
    expect(suggestObject("PAGAMENTO DIVERSOS")).toBeNull();
  });

  it("cada item tem custeio ou capital, e o capital vem antes na busca (bem que dura ganha de 'material')", () => {
    expect(PDDE_OBJECTS.every((o) => o.economic === "CAPITAL" || o.economic === "CUSTEIO")).toBe(true);
    expect(suggestObject("NOTEBOOK E MATERIAL")).toMatchObject({ economic: "CAPITAL" });
  });

  it("a entrada diz o programa, custeio ou capital e se e rendimento", () => {
    expect(suggestCredit("CREDITO FNDE PDDE BASICO CUSTEIO")).toEqual({ kind: "TRANSFER", program: "BASICO", economic: "CUSTEIO" });
    expect(suggestCredit("CRÉDITO PDDE Qualidade CAPITAL")).toEqual({ kind: "TRANSFER", program: "QUALIDADE", economic: "CAPITAL" });
    expect(suggestCredit("RENDIMENTO APLICACAO FINANCEIRA")).toEqual({ kind: "YIELD", program: null, economic: null });
    expect(suggestCredit("CREDITO DIVERSOS")).toEqual({ kind: "TRANSFER", program: null, economic: null });
  });

  it("plain tira acento e caixa", () => {
    expect(plain("Instalação ÁGUA")).toBe("instalacao agua");
  });
});
