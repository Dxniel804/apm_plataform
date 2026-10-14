"use client";

import { useState } from "react";
import { TextField } from "@/components/ui/TextField";
import { centsFromDigits, formatBRLNumber } from "@/lib/money";

/** Limite do banco para o custo de uma unidade: R$ 10.000,00. */
export const MAX_COST_CENTS = 1_000_000;

interface Props {
  /** `null` = custo nao informado (diferente de R$ 0,00, um brinde que nao custa nada). */
  value: number | null;
  onChange: (cents: number | null) => void;
  error?: string;
  name: string;
}

/**
 * O custo de uma unidade para a APM. Vazio quer dizer "nao informado": o lucro da campanha so aparece quando todo
 * produto vendido tem custo. E uma medida de gestao, nao um lancamento no caixa.
 */
export function CostField({ value, onChange, error, name }: Props) {
  const [digits, setDigits] = useState(value === null ? "" : String(value));
  return (
    <TextField
      label="Custo por unidade"
      optional
      name={name}
      prefix="R$"
      inputMode="numeric"
      autoComplete="off"
      placeholder="Não informado"
      value={digits === "" ? "" : formatBRLNumber(centsFromDigits(digits))}
      onChange={(e) => {
        const next = e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "").slice(0, 8);
        setDigits(next);
        onChange(next === "" ? null : centsFromDigits(next));
      }}
      hint="Quanto cada unidade custa para a APM. Serve para mostrar o lucro da campanha; não vira lançamento no caixa."
      error={error}
    />
  );
}
