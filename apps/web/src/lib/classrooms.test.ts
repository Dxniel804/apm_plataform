import { describe, expect, it } from "vitest";
import { CLASS_YEARS, joinClassroom, splitClassroom } from "./classrooms";

describe("classrooms", () => {
  it("junta o ano e a turma em um texto so", () => {
    expect(joinClassroom("4º ano", "B")).toBe("4º ano B");
    expect(joinClassroom("4º ano", "")).toBe("4º ano");
    expect(joinClassroom("", "B")).toBe("");
  });

  it("separa de volta, inclusive os anos do Ensino Medio que tem mais palavras", () => {
    expect(splitClassroom("4º ano B")).toEqual({ year: "4º ano", group: "B" });
    expect(splitClassroom("1º ano do Ensino Médio C")).toEqual({ year: "1º ano do Ensino Médio", group: "C" });
    expect(splitClassroom("1º ano")).toEqual({ year: "1º ano", group: "" });
    expect(splitClassroom("Educação Infantil")).toEqual({ year: "Educação Infantil", group: "" });
  });

  it("um texto fora da lista (dado antigo) volta sem ano, e todo ano da lista faz a volta inteira", () => {
    expect(splitClassroom("quarto ano b")).toEqual({ year: "", group: "" });
    for (const y of CLASS_YEARS) expect(splitClassroom(joinClassroom(y, "D"))).toEqual({ year: y, group: "D" });
  });
});
