"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { PhotoPicker } from "@/components/ui/PhotoPicker";
import { SelectField, TextAreaField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { RequestCategory } from "@/lib/api/types";
import { CATEGORY_LABELS, CATEGORY_ORDER, describeRequestError } from "@/lib/request-labels";

interface Props {
  schoolId: string;
  open: boolean;
  onClose: () => void;
  /** Chamado com o id da solicitacao criada e um aviso (as fotos que nao subiram, se houver). */
  onSaved: (requestId: string, note: string) => void;
}

/**
 * "Nova solicitacao": categoria, titulo, descricao e fotos. Cria o pedido e depois envia as fotos uma a uma pela
 * API (o pedido ja existe, entao uma foto que falha nao perde o resto). O NOME de quem envia nunca e pedido: a API
 * usa o usuario da sessao. As fotos ficam so na memoria do navegador ate aqui.
 */
export function RequestForm({ schoolId, open, onClose, onSaved }: Props) {
  const [category, setCategory] = useState<RequestCategory | "">("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setGeneral(null);
    const problems: Record<string, string> = {};
    if (!category) problems.category = "Escolha uma categoria.";
    if (!title.trim()) problems.title = "Escreva o título do pedido.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;

    setBusy(true);
    const created = await api.requests.create(schoolId, { category: category as RequestCategory, title: title.trim(), description: description.trim() || undefined });
    if (!created.ok) {
      setBusy(false);
      const text = describeRequestError(created.error);
      setErrors(text.fields);
      return setGeneral(text.general);
    }
    let failed = 0;
    let reason: string | null = null;
    for (const photo of photos) {
      const sent = await api.requests.upload(schoolId, created.data.id, photo);
      if (!sent.ok) {
        failed += 1;
        reason ??= describeRequestError(sent.error).general;
      }
    }
    setBusy(false);
    const note =
      failed === 0
        ? "Solicitação enviada para a gestão."
        : `Solicitação enviada, mas ${failed === 1 ? "uma foto não foi enviada" : `${failed} fotos não foram enviadas`}. ${reason ?? ""} Abra a solicitação para anexar de novo.`.trim();
    setCategory("");
    setTitle("");
    setDescription("");
    setPhotos([]);
    onSaved(created.data.id, note);
  }

  return (
    <Modal open={open} onClose={() => !busy && onClose()} label="Nova solicitação" initialFocus={titleRef}>
      <form method="post" noValidate onSubmit={(event) => void submit(event)} className="space-y-5 p-5 sm:p-8">
        <h2 className="text-title text-brand-800">Nova solicitação</h2>
        <p className="-mt-2 text-body text-ink-2">Peça algo para a gestão da escola. Dá para anexar fotos.</p>

        <SelectField id="request-category" label="Categoria" value={category} onChange={(e) => setCategory(e.target.value as RequestCategory | "")} error={errors.category}>
          <option value="">Escolha…</option>
          {CATEGORY_ORDER.map((key) => (
            <option key={key} value={key}>
              {CATEGORY_LABELS[key]}
            </option>
          ))}
        </SelectField>
        <TextField label="Título" name="title" inputRef={titleRef} autoComplete="off" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
        <TextAreaField label="Descrição" name="description" optional maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
        <PhotoPicker photos={photos} onChange={setPhotos} disabled={busy} />

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
            {busy ? "Enviando…" : "Enviar solicitação"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
