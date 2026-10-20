"use client";

import { useRef, type ReactNode, type Ref } from "react";
import { Button } from "@/components/ui/Button";
import { BuildingIcon, MailIcon, PhoneIcon, UserIcon } from "@/components/ui/icons";
import { TextField } from "@/components/ui/TextField";
import type { PublicSchool } from "@/lib/api/types";
import {
  FIELD_LABELS,
  FIELD_MAX_LENGTH,
  visibleFields,
  type IdentificationErrors,
  type IdentificationField,
  type IdentificationValues,
} from "@/lib/validation";
import { ClassroomField } from "./ClassroomField";
import { StickyActions } from "./FlowChrome";

const AUTOCOMPLETE: Record<IdentificationField, string> = {
  guardianName: "name",
  studentName: "off",
  classroom: "off",
  contributorEmail: "email",
  contributorPhone: "tel",
};

const PLACEHOLDERS: Record<IdentificationField, string> = {
  guardianName: "Como está no seu documento",
  studentName: "Nome do aluno ou da aluna",
  classroom: "Ex.: 4º ano B",
  contributorEmail: "voce@exemplo.com.br",
  contributorPhone: "(11) 91234-5678",
};

const FIELD_ICONS: Record<IdentificationField, ReactNode> = {
  guardianName: <UserIcon size={18} />,
  studentName: <UserIcon size={18} />,
  classroom: <BuildingIcon size={18} />,
  contributorEmail: <MailIcon size={18} />,
  contributorPhone: <PhoneIcon size={18} />,
};

const INPUT_TYPE: Partial<Record<IdentificationField, { type: string; inputMode: "email" | "tel" }>> = {
  contributorEmail: { type: "email", inputMode: "email" },
  contributorPhone: { type: "tel", inputMode: "tel" },
};

interface IdentificationStepProps {
  school: PublicSchool;
  values: IdentificationValues;
  errors: IdentificationErrors;
  headingRef: Ref<HTMLHeadingElement>;
  onChange: (field: IdentificationField, value: string) => void;
  onBack: () => void;
  onContinue: (focusField: (field: IdentificationField) => void) => void;
}

export function IdentificationStep({
  school,
  values,
  errors,
  headingRef,
  onChange,
  onBack,
  onContinue,
}: IdentificationStepProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const fields = visibleFields(school.identification);
  const hasOptional = fields.some((f) => school.identification[f] === "OPTIONAL");

  const focusField = (field: IdentificationField) => {
    const element = formRef.current?.elements.namedItem(field);
    if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement) element.focus();
  };

  return (
    <form
      method="post"
      ref={formRef}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        onContinue(focusField);
      }}
    >
      <h2 ref={headingRef} tabIndex={-1} className="text-title outline-none">
        Quem está contribuindo?
      </h2>
      <p className="mt-2 max-w-[52ch] text-body text-ink-2">
        Esses dados ajudam a gestão a identificar o pagamento. Você não precisa criar conta nem fazer login.
        {hasOptional && " Campos marcados como opcionais podem ficar em branco."}
      </p>

      <div className="mt-6 space-y-[1.125rem]">
        {fields.map((field) =>
          field === "classroom" ? (
            <ClassroomField key={field} name={field} optional={school.identification[field] === "OPTIONAL"} value={values[field] ?? ""} onChange={(v) => onChange(field, v)} error={errors[field]} />
          ) : (
          <TextField
            key={field}
            name={field}
            icon={FIELD_ICONS[field]}
            label={FIELD_LABELS[field]}
            optional={school.identification[field] === "OPTIONAL"}
            autoComplete={AUTOCOMPLETE[field]}
            // Dado de crianca: sem corretor ortografico (que manda o texto a servicos externos em alguns
            // navegadores) e sem historico de autopreenchimento para aluno e turma.
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize={INPUT_TYPE[field] ? "none" : "words"}
            type={INPUT_TYPE[field]?.type}
            inputMode={INPUT_TYPE[field]?.inputMode}
            placeholder={PLACEHOLDERS[field]}
            maxLength={FIELD_MAX_LENGTH[field]}
            value={values[field] ?? ""}
            onChange={(e) => onChange(field, e.target.value)}
            error={errors[field]}
          />
          ),
        )}
      </div>

      <StickyActions>
        <Button variant="secondary" className="w-28 shrink-0 sm:w-auto sm:min-w-32" onClick={onBack}>
          Voltar
        </Button>
        <Button type="submit" variant="solid" className="flex-1 sm:min-w-56 sm:flex-none">
          Continuar
        </Button>
      </StickyActions>
    </form>
  );
}
