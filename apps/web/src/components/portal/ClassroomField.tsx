"use client";

import { SelectField } from "@/components/ui/TextField";
import { CLASS_GROUPS, CLASS_YEARS, joinClassroom, splitClassroom } from "@/lib/classrooms";

interface Props {
  /** O nome do campo (`classroom`): o ano e o que recebe o foco e o erro. */
  name: string;
  value: string;
  optional?: boolean;
  error?: string;
  onChange: (value: string) => void;
}

/** O ano e a turma do aluno em duas listas, no lugar de um campo de texto. O valor e um texto so: "4º ano B". */
export function ClassroomField({ name, value, optional, error, onChange }: Props) {
  const { year, group } = splitClassroom(value);
  return (
    <div className="grid grid-cols-[1fr_auto] gap-3">
      <SelectField id={`${name}-year`} name={name} label="Ano do aluno" optional={optional} error={error} value={year} onChange={(e) => onChange(joinClassroom(e.target.value, e.target.value === "" ? "" : group))}>
        <option value="">Escolha</option>
        {CLASS_YEARS.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </SelectField>
      <SelectField id={`${name}-group`} name={`${name}-group`} label="Turma" optional disabled={year === ""} value={group} onChange={(e) => onChange(joinClassroom(year, e.target.value))} wrapperClassName="w-28">
        <option value="">—</option>
        {CLASS_GROUPS.map((g) => (
          <option key={g} value={g}>
            {g}
          </option>
        ))}
      </SelectField>
    </div>
  );
}
