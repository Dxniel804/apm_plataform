"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { TextAreaField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import { describeCampaignError } from "@/lib/campaign-labels";

interface Props {
  schoolId: string;
  open: boolean;
  onClose: () => void;
  /** Chamado com o id da campanha criada (um rascunho). */
  onSaved: (campaignId: string) => void;
}

/** "Nova campanha": titulo, texto e datas. Nasce RASCUNHO: nada fica a venda ate a gestao pedir. */
export function CampaignForm({ schoolId, open, onClose, onSaved }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setGeneral(null);
    const problems: Record<string, string> = {};
    if (!title.trim()) problems.title = "Escreva o título da campanha.";
    if (startsOn && endsOn && startsOn > endsOn) problems.ends_on = "A data de fim não pode ser antes da data de início.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;

    setBusy(true);
    const created = await api.campaigns.create(schoolId, {
      title: title.trim(),
      description: description.trim() || undefined,
      startsOn: startsOn || undefined,
      endsOn: endsOn || undefined,
    });
    setBusy(false);
    if (!created.ok) {
      const text = describeCampaignError(created.error);
      setErrors(text.fields);
      return setGeneral(text.general);
    }
    setTitle("");
    setDescription("");
    setStartsOn("");
    setEndsOn("");
    onSaved(created.data.id);
  }

  return (
    <Modal open={open} onClose={() => !busy && onClose()} label="Nova campanha" initialFocus={titleRef}>
      <form method="post" noValidate onSubmit={(event) => void submit(event)} className="space-y-5 p-5 sm:p-8">
        <h2 className="text-title text-brand-800">Nova campanha</h2>
        <p className="-mt-2 text-body text-ink-2">
          Uma festa, um kit, uma rifa. Você escreve o texto, põe os produtos com o preço e, quando estiver pronta, coloca à venda.
        </p>
        <TextField label="Título" name="campaign-title" inputRef={titleRef} autoComplete="off" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
        <TextAreaField label="Texto para as famílias" name="campaign-description" optional maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Começa em" optional name="campaign-starts" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} error={errors.starts_on} />
          <TextField label="Termina em" optional name="campaign-ends" type="date" value={endsOn} onChange={(e) => setEndsOn(e.target.value)} error={errors.ends_on} />
        </div>
        <div aria-live="polite">
          {general && (
            <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
              {general}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button variant="plain" size="md" onClick={onClose} disabled={busy} className="rounded-full!">
            Cancelar
          </Button>
          <Button type="submit" size="md" disabled={busy} aria-busy={busy} className="rounded-full!">
            {busy ? "Criando…" : "Criar rascunho"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
