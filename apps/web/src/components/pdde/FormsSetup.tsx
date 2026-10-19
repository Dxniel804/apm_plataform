"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiError, ApiResult } from "@/lib/api/types";
import type { PddeCarryover, PddeEntity, PddeProgram } from "@/lib/api/pdde";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";

const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");
const PROGRAMS: Record<PddeProgram, string> = { BASICO: "PDDE Básico", EQUIDADE: "PDDE Equidade", QUALIDADE: "PDDE Qualidade", CONECTADO: "Educação Conectada", OUTRO: "Outro programa" };

function describe(error: ApiError): string {
  if (error.kind === "network" || error.kind === "timeout") return "Não foi possível falar com o servidor. Nada foi alterado.";
  if (error.status === 403) return "O seu perfil não mexe no PDDE.";
  if (error.status === 422) return "Confira os dados: o CNPJ precisa ser válido e a UF ser uma sigla de estado.";
  return "Não foi possível concluir. Tente de novo.";
}

function Money({ label, cents, onChange }: { label: string; cents: number; onChange: (v: number) => void }) {
  return <TextField label={label} name={label} prefix="R$" inputMode="numeric" autoComplete="off" placeholder="0,00" value={cents === 0 ? "" : formatBRLNumber(cents)} onChange={(e) => onChange(centsFromDigits(e.target.value))} />;
}

function Entity({ schoolId }: { schoolId: string }) {
  const [loaded, setLoaded] = useState<ApiResult<PddeEntity | null> | null>(null);
  const [form, setForm] = useState({ legalName: "", cnpj: "", address: "", city: "", state: "SP" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.pdde.entity(schoolId).then((res) => {
      if (cancelled) return;
      setLoaded(res);
      if (res.ok && res.data) setForm({ legalName: res.data.legalName, cnpj: res.data.cnpj, address: res.data.address, city: res.data.city, state: res.data.state });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (Object.values(form).some((v) => v.trim() === "")) return setError("Preencha todos os campos.");
    setBusy(true);
    setError(null);
    setNotice(null);
    const r = await api.pdde.saveEntity(schoolId, { ...form, legalName: form.legalName.trim(), address: form.address.trim(), city: form.city.trim() });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    setNotice("Dados da entidade salvos.");
  }

  const set = (key: keyof typeof form) => (value: string) => setForm((prev) => ({ ...prev, [key]: value }));
  return (
    <details className="rounded-[var(--r-md)] border border-line px-4 py-3">
      <summary className="cursor-pointer text-sub font-semibold text-brand-800">
        Dados da entidade para os formulários {loaded?.ok && loaded.data === null ? "(faltam)" : ""}
      </summary>
      <form method="post" onSubmit={(e) => void submit(e)} className="mt-3 space-y-4">
        <p className="max-w-[62ch] text-sub text-ink-2">Saem nos campos 03 a 07 do formulário do FNDE. O nome é o do cartão do CNPJ.</p>
        <TextField label="Nome (como no cartão do CNPJ)" name="legal-name" maxLength={120} value={form.legalName} onChange={(e) => set("legalName")(e.target.value)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="CNPJ" name="cnpj" inputMode="numeric" autoComplete="off" maxLength={24} value={form.cnpj} onChange={(e) => set("cnpj")(e.target.value)} />
          <TextField label="Endereço" name="address" maxLength={200} value={form.address} onChange={(e) => set("address")(e.target.value)} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Município" name="city" maxLength={80} value={form.city} onChange={(e) => set("city")(e.target.value)} />
          <SelectField id="entity-state" label="UF" value={form.state} onChange={(e) => set("state")(e.target.value)}>
            {UFS.map((uf) => (
              <option key={uf} value={uf}>
                {uf}
              </option>
            ))}
          </SelectField>
        </div>
        <Button type="submit" variant="plain" size="md" disabled={busy} className="rounded-full!">
          Salvar os dados
        </Button>
        <div aria-live="polite">
          {error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}
          {notice && <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
        </div>
      </form>
    </details>
  );
}

function Carryover({ schoolId, year }: { schoolId: string; year: number }) {
  const [version, setVersion] = useState(0);
  const [loaded, setLoaded] = useState<{ year: number; res: ApiResult<PddeCarryover[]> } | null>(null);
  const [program, setProgram] = useState<PddeProgram>("BASICO");
  const [label, setLabel] = useState("");
  const [custeio, setCusteio] = useState(0);
  const [capital, setCapital] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.pdde.carryovers(schoolId, year).then((res) => !cancelled && setLoaded({ year, res }));
    return () => {
      cancelled = true;
    };
  }, [schoolId, year, version]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (program === "OUTRO" && label.trim() === "") return setError("Diga o nome do programa.");
    setBusy(true);
    setError(null);
    setNotice(null);
    const r = await api.pdde.saveCarryover(schoolId, year, { program, programLabel: program === "OUTRO" ? label.trim() : null, custeioCents: custeio, capitalCents: capital });
    setBusy(false);
    if (!r.ok) return setError(describe(r.error));
    setNotice("Saldo salvo.");
    setVersion((n) => n + 1);
  }

  const list = loaded?.year === year && loaded.res.ok ? loaded.res.data : [];
  return (
    <details className="rounded-[var(--r-md)] border border-line px-4 py-3">
      <summary className="cursor-pointer text-sub font-semibold text-brand-800">Saldo que veio de {year - 1} para {year}</summary>
      <form method="post" onSubmit={(e) => void submit(e)} className="mt-3 space-y-4">
        <p className="max-w-[62ch] text-sub text-ink-2">
          Sai no campo 08 do formulário. Digite o que sobrou do ano passado em cada programa, se a escola já tinha saldo quando começou a usar o sistema. Sem isso, o formulário usa o que os extratos de anos anteriores mostram, ou zero.
        </p>
        {list.length > 0 && (
          <ul aria-label="Saldos informados" className="space-y-1 text-sub">
            {list.map((c) => (
              <li key={`${c.program}-${c.programLabel ?? ""}`}>
                {c.program === "OUTRO" ? (c.programLabel ?? PROGRAMS.OUTRO) : PROGRAMS[c.program]}: custeio {formatBRL(c.custeioCents)} · capital {formatBRL(c.capitalCents)}
              </li>
            ))}
          </ul>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField id="carry-program" label="Programa" value={program} onChange={(e) => setProgram(e.target.value as PddeProgram)}>
            {(Object.keys(PROGRAMS) as PddeProgram[]).map((p) => (
              <option key={p} value={p}>
                {PROGRAMS[p]}
              </option>
            ))}
          </SelectField>
          {program === "OUTRO" && <TextField label="Nome do programa" name="carry-label" maxLength={60} value={label} onChange={(e) => setLabel(e.target.value)} />}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Money label="Saldo de custeio" cents={custeio} onChange={setCusteio} />
          <Money label="Saldo de capital" cents={capital} onChange={setCapital} />
        </div>
        <Button type="submit" variant="plain" size="md" disabled={busy} className="rounded-full!">
          Salvar o saldo
        </Button>
        <div aria-live="polite">
          {error && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}
          {notice && <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
        </div>
      </form>
    </details>
  );
}

/** O que o formulario oficial do FNDE pede e o resto do PDDE nao tem: a entidade e o saldo do ano anterior. */
export function FormsSetup({ schoolId, year }: { schoolId: string; year: number }) {
  return (
    <div className="mt-4 space-y-3">
      <Entity schoolId={schoolId} />
      <Carryover schoolId={schoolId} year={year} />
    </div>
  );
}
