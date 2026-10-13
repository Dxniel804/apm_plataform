"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { PhotoPicker } from "@/components/ui/PhotoPicker";
import { StatusPill } from "@/components/ui/StatusPill";
import { TextAreaField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiResult, StaffRequestDetail } from "@/lib/api/types";
import { formatDateShort, formatDateTime } from "@/lib/format";
import { CATEGORY_LABELS, MAX_PHOTOS, describeRequestError, requestStatusView } from "@/lib/request-labels";
import { RequestPhotos } from "./RequestPhotos";

interface Props {
  schoolId: string;
  requestId: string;
  /** Usuario da sessao: so serve para NAO oferecer ao autor o que a API recusa. A API continua recusando. */
  userId: string;
  permissions: string[];
  /** Avisa a lista que algo mudou (ela recarrega e mostra a mensagem: o pedido pode sair do filtro). */
  onChanged: (message?: string) => void;
}

function ResolveForm({ busy, error, onSubmit, onCancel }: { busy: boolean; error: string | null; onSubmit: (note: string) => void; onCancel: () => void }) {
  const [note, setNote] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  return (
    <FormModal title="Marcar como resolvida" intro="Quem abriu o pedido lê a sua resposta. Ela é opcional, mas ajuda a saber o que foi feito." onClose={onCancel} busy={busy}>
      <form
        method="post"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const text = note.trim();
          if (text.length > 1000) return setLocal("A resposta pode ter até 1000 caracteres.");
          setLocal(null);
          onSubmit(text);
        }}
        className="space-y-5"
      >
        <TextAreaField label="Resposta para quem pediu" name="resolution-note" optional rows={4} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} error={local ?? error ?? undefined} />
        <FormButtons onCancel={onCancel} cancelLabel="Voltar" submitLabel="Marcar como resolvida" pendingLabel="Salvando…" pending={busy} />
      </form>
    </FormModal>
  );
}

/**
 * Detalhe de uma solicitacao com as acoes que cabem a QUEM ve, pelas permissoes da sessao e pela autoria. O site
 * nunca decide o estado: depois de cada acao mostra o que a API devolveu. A API segue sendo a autoridade: 403,
 * 404, 409 e 422 viram texto em portugues e a tela nao quebra.
 */
export function RequestDetailPanel({ schoolId, requestId, userId, permissions, onChanged }: Props) {
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<StaffRequestDetail> } | null>(null);
  const [version, setVersion] = useState(0);
  const [override, setOverride] = useState<StaffRequestDetail | null>(null);
  const [resolving, setResolving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [extra, setExtra] = useState<File[]>([]);

  const key = `${schoolId}|${requestId}|${version}`;
  useEffect(() => {
    let cancelled = false;
    void api.requests.get(schoolId, requestId).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, requestId, key]);

  if (loaded?.key !== key && !override) return <p role="status" className="px-5 py-4 text-sub text-ink-2">Carregando a solicitação…</p>;
  const res = loaded?.key === key ? loaded.res : null;
  if (res && !res.ok) return <p role="alert" className="px-5 py-4 text-sub font-medium text-bad">{describeRequestError(res.error).general}</p>;
  const d = override ?? (res && res.ok ? res.data : null);
  if (!d) return null;

  const has = (p: string) => permissions.includes(p);
  const own = d.authorUserId === userId;
  const open = d.status === "OPEN" || d.status === "IN_PROGRESS";
  const status = requestStatusView(d.status);
  const canAttach = has("requests:submit") && own && open;
  const canCancel = canAttach;
  const canStart = has("requests:manage") && d.status === "OPEN";
  const canResolve = has("requests:manage") && open;

  function changed(next: StaffRequestDetail, message?: string) {
    setOverride(next);
    setResolving(false);
    setError(null);
    setFieldError(null);
    onChanged(message);
  }

  async function run(name: string, call: () => Promise<ApiResult<StaffRequestDetail>>, message: string) {
    if (busy) return;
    setBusy(name);
    setError(null);
    setFieldError(null);
    const result = await call();
    setBusy(null);
    if (result.ok) return changed(result.data, message);
    const text = describeRequestError(result.error);
    setError(text.general);
    setFieldError(Object.values(text.fields)[0] ?? null);
    // Estado que mudou por baixo: recarrega para a tela voltar a bater com a API.
    if (result.error.status === 409) {
      setOverride(null);
      setVersion((n) => n + 1);
    }
  }

  async function sendPhotos() {
    if (busy || extra.length === 0) return;
    setBusy("photos");
    setError(null);
    let failed: string | null = null;
    for (const photo of extra) {
      const sent = await api.requests.upload(schoolId, d!.id, photo);
      if (!sent.ok) failed ??= describeRequestError(sent.error).general;
    }
    setBusy(null);
    setExtra([]);
    const fresh = await api.requests.get(schoolId, d!.id);
    if (fresh.ok) changed(fresh.data, failed ? undefined : "Fotos anexadas.");
    else setVersion((n) => n + 1);
    if (failed) setError(failed);
  }

  const fact = (label: string, value: React.ReactNode) => (
    <div className="min-w-0">
      <dt className="text-sub text-ink-2">{label}:</dt>
      <dd className="mt-0.5 text-[1.0625rem] font-bold text-brand-800 [overflow-wrap:anywhere] sm:text-[1.25rem]">{value}</dd>
    </div>
  );

  return (
    <div className="border-t border-line px-5 py-6 sm:px-8 sm:py-8" data-testid="request-detail">
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill tone={status.tone}>{status.label}</StatusPill>
        <span className="text-foot text-ink-2">aberta em {formatDateShort(d.createdAt)}</span>
      </div>

      <dl className="mt-5 grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
        {fact("Categoria", CATEGORY_LABELS[d.category])}
        {own && fact("Aberta por", "você")}
        {d.startedAt && fact("Em atendimento desde", formatDateTime(d.startedAt))}
        {d.resolvedAt && fact("Resolvida em", formatDateTime(d.resolvedAt))}
      </dl>

      {d.description && <p className="mt-5 whitespace-pre-line text-body text-ink [overflow-wrap:anywhere]">{d.description}</p>}

      <h2 className="mt-6 text-headline">Fotos</h2>
      <RequestPhotos schoolId={schoolId} requestId={d.id} photos={d.photos} />

      {d.resolutionNote && (
        <p role="note" className="mt-5 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub text-ok">
          <strong className="font-semibold">Resposta da gestão:</strong> {d.resolutionNote}
        </p>
      )}
      {d.status === "RESOLVED" && !d.resolutionNote && own && (
        <p role="note" className="mt-5 rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub text-ok">
          A gestão marcou esta solicitação como resolvida.
        </p>
      )}

      {canAttach && d.photos.length < MAX_PHOTOS && (
        <div className="mt-6">
          <PhotoPicker photos={extra} onChange={setExtra} max={MAX_PHOTOS - d.photos.length} disabled={busy !== null} label="Anexar mais fotos" />
          {extra.length > 0 && (
            <Button size="md" onClick={() => void sendPhotos()} disabled={busy !== null} aria-busy={busy === "photos"} className="mt-3 min-h-12 rounded-full! px-7">
              {busy === "photos" ? "Enviando…" : extra.length === 1 ? "Enviar a foto" : "Enviar as fotos"}
            </Button>
          )}
        </div>
      )}

      <div aria-live="polite">
        {error && <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{error}</p>}
      </div>

      {(canStart || canResolve || canCancel) && (
        <div className="mt-6 flex flex-wrap gap-3">
          {canStart && (
            <Button size="md" variant="secondary" className="min-h-12 rounded-full! px-7" onClick={() => void run("start", () => api.requests.start(schoolId, d.id), "Atendimento iniciado.")} disabled={busy !== null} aria-busy={busy === "start"}>
              {busy === "start" ? "Salvando…" : "Iniciar atendimento"}
            </Button>
          )}
          {canResolve && (
            <Button size="md" className="min-h-12 rounded-full! px-7" onClick={() => setResolving(true)} disabled={busy !== null}>
              Marcar como resolvida
            </Button>
          )}
          {canCancel && (
            <Button size="md" variant="plain" className="min-h-12 rounded-full! px-7" onClick={() => void run("cancel", () => api.requests.cancel(schoolId, d.id), "Solicitação cancelada.")} disabled={busy !== null}>
              Cancelar solicitação
            </Button>
          )}
        </div>
      )}
      {resolving && (
        <ResolveForm busy={busy === "resolve"} error={fieldError} onCancel={() => setResolving(false)} onSubmit={(note) => void run("resolve", () => api.requests.resolve(schoolId, d.id, note || undefined), "Solicitação resolvida.")} />
      )}
    </div>
  );
}
