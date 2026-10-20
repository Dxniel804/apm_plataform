/**
 * Os anos e as turmas que o responsavel escolhe (em vez de digitar), para a turma nunca sair "4 ano b", "4o B" ou
 * "quarto ano". O texto guardado e um so, no formato "4º ano B" (o campo `class_name` da API).
 */
export const CLASS_YEARS: readonly string[] = [
  "Educação Infantil",
  "1º ano",
  "2º ano",
  "3º ano",
  "4º ano",
  "5º ano",
  "6º ano",
  "7º ano",
  "8º ano",
  "9º ano",
  "1º ano do Ensino Médio",
  "2º ano do Ensino Médio",
  "3º ano do Ensino Médio",
];

export const CLASS_GROUPS: readonly string[] = ["A", "B", "C", "D", "E", "F"];

/** "4º ano" + "B" = "4º ano B"; sem ano, vazio (a turma sozinha nao diz nada). */
export function joinClassroom(year: string, group: string): string {
  if (year === "") return "";
  return group === "" ? year : `${year} ${group}`;
}

/** O inverso: separa "4º ano B" no ano e na turma. Um texto que nao esta nas listas (dado antigo) volta sem ano. */
export function splitClassroom(value: string): { year: string; group: string } {
  const year = [...CLASS_YEARS].sort((a, b) => b.length - a.length).find((y) => value === y || value.startsWith(`${y} `));
  if (!year) return { year: "", group: "" };
  const rest = value.slice(year.length).trim();
  return { year, group: CLASS_GROUPS.includes(rest) ? rest : "" };
}
