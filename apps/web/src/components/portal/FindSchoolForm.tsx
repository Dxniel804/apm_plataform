"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { ArrowRightIcon } from "@/components/ui/icons";
import { TextField } from "@/components/ui/TextField";
import { isPlausibleSlug } from "@/lib/api/token";

/**
 * Para o responsavel que chegou sem o link da escola: ele digita o codigo (o slug do link) e vai ao portal.
 * Nao ha lista de escolas (nao revelamos quais usam o sistema); se o codigo nao existir, o proprio portal
 * responde "escola nao encontrada" com o mesmo 404 de qualquer outro codigo.
 */
export function FindSchoolForm() {
  const router = useRouter();
  const codeRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | undefined>();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Tolera o link inteiro colado e maiusculas/espacos: pega o ultimo trecho depois de /escola/.
    const raw = (codeRef.current?.value ?? "").trim().toLowerCase();
    const code = raw.replace(/^.*\/escola\//, "").replace(/[/?#].*$/, "");
    if (!code) {
      setError("Informe o código da sua escola.");
      return codeRef.current?.focus();
    }
    if (!isPlausibleSlug(code)) {
      setError("Esse código não parece certo. Use só letras, números e hífens, como no link da escola.");
      return codeRef.current?.focus();
    }
    setError(undefined);
    router.push(`/escola/${code}`);
  }

  return (
    <form method="post" noValidate onSubmit={onSubmit} className="mt-8 space-y-5">
      <TextField
        variant="filled"
        label="Código da escola"
        name="school"
        inputMode="text"
        autoComplete="off"
        spellCheck={false}
        autoCapitalize="none"
        autoCorrect="off"
        placeholder="demo-aurora"
        inputRef={codeRef}
        error={error}
      />
      <Button type="submit" className="w-full">
        Continuar
        <ArrowRightIcon size={18} />
      </Button>
    </form>
  );
}
