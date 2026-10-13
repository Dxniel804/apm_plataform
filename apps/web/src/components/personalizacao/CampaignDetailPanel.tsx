"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { Modal } from "@/components/ui/Modal";
import { StatusPill } from "@/components/ui/StatusPill";
import { TextAreaField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiResult, CampaignDetail } from "@/lib/api/types";
import { MAX_ITEMS, MAX_PRICE_CENTS, MIN_PRICE_CENTS, campaignStatusView, describeCampaignError, describePeriod } from "@/lib/campaign-labels";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { CampaignImage } from "./CampaignImage";
import { CampaignItemRow } from "./CampaignItemRow";
import { CampaignPreview } from "./CampaignPreview";
import { ImageButtons } from "./ImageButtons";

interface Props {
  schoolId: string;
  campaignId: string;
  /** Avisa a lista que algo mudou (ela recarrega as contagens e mostra a mensagem). */
  onChanged: (message?: string) => void;
}

type Confirming = "activate" | "end" | null;

/**
 * O editor de uma campanha: texto e datas, capa, produtos (com imagem, preco e limite por pedido), pre-visualizacao
 * e as duas acoes que importam, "Pôr à venda" e "Encerrar". O site nunca decide estado nem preco: depois de cada
 * acao mostra a campanha que a API devolveu. A API segue sendo a autoridade (403, 404, 409 e 422 viram texto).
 */
export function CampaignDetailPanel({ schoolId, campaignId, onChanged }: Props) {
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<CampaignDetail> } | null>(null);
  const [version, setVersion] = useState(0);
  const [override, setOverride] = useState<CampaignDetail | null>(null);
  const [confirming, setConfirming] = useState<Confirming>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const key = `${schoolId}|${campaignId}|${version}`;
  useEffect(() => {
    let cancelled = false;
    void api.campaigns.get(schoolId, campaignId).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, campaignId, key]);

  if (loaded?.key !== key && !override) return <p role="status" className="px-5 py-4 text-sub text-ink-2">Carregando a campanha…</p>;
  const res = loaded?.key === key ? loaded.res : null;
  if (res && !res.ok) return <p role="alert" className="px-5 py-4 text-sub font-medium text-bad">{describeCampaignError(res.error).general}</p>;
  const campaign = override ?? (res && res.ok ? res.data : null);
  if (!campaign) return null;
  const detail: CampaignDetail = campaign;

  const ended = detail.status === "ENDED";
  const view = campaignStatusView(detail.status);
  const period = describePeriod(detail.startsOn, detail.endsOn);

  function changed(next: CampaignDetail, message?: string) {
    setOverride(next);
    setProblem(null);
    setNotice(message ?? null);
    onChanged(message);
  }

  function stale() {
    setOverride(null);
    setVersion((n) => n + 1);
  }

  async function run(name: Confirming & string, call: () => Promise<ApiResult<CampaignDetail>>, message: string) {
    if (busy) return;
    setBusy(name);
    setProblem(null);
    const result = await call();
    setBusy(null);
    setConfirming(null);
    if (result.ok) return changed(result.data, message);
    const text = describeCampaignError(result.error);
    setProblem(text.general ?? Object.values(text.fields)[0] ?? null);
    if (result.error.status === 409) stale();
  }

  return (
    <div className="space-y-8 border-t border-line px-5 py-6 sm:px-8 sm:py-8">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <StatusPill tone={view.tone}>{view.label}</StatusPill>
        <p className="min-w-0 flex-1 basis-48 text-sub text-ink-2">
          {period ? `${period} · ` : ""}
          {detail.paidOrdersCount} {detail.paidOrdersCount === 1 ? "pedido pago" : "pedidos pagos"}
          {detail.paidOrdersCount > 0 ? ` · ${formatBRL(detail.paidCents)}` : ""}
        </p>
        {!ended && (
          <div className="flex flex-wrap gap-3">
            {detail.status === "DRAFT" && (
              <Button size="md" onClick={() => setConfirming("activate")} disabled={busy !== null} className="rounded-full!">
                Pôr à venda
              </Button>
            )}
            <Button variant="secondary" size="md" onClick={() => setConfirming("end")} disabled={busy !== null} className="rounded-full!">
              Encerrar campanha
            </Button>
          </div>
        )}
      </div>

      <div aria-live="polite">
        {notice && !problem && (
          <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">
            {notice}
          </p>
        )}
        {problem && (
          <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
            {problem}
          </p>
        )}
      </div>

      {ended && (
        <p role="note" className="rounded-[var(--r-md)] bg-info-soft px-4 py-3 text-sub text-info">
          Esta campanha foi encerrada: nada mais é vendido e ela não muda. Os pedidos já feitos continuam no caixa.
        </p>
      )}

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_23rem] xl:gap-10">
        <div className="min-w-0 space-y-8">
          <TextAndDates key={`${detail.id}|${detail.updatedAt}`} schoolId={schoolId} detail={detail} disabled={ended || busy !== null} onDetail={changed} onProblem={setProblem} onStale={stale} />

          <section aria-labelledby={`cover-${detail.id}`}>
            <h2 id={`cover-${detail.id}`} className="text-heading">
              Capa
            </h2>
            <p className="mt-1 text-sub text-ink-2">A imagem de destaque da campanha. A API tira da foto o local e os dados do aparelho antes de guardar.</p>
            <div className="mt-4 flex flex-wrap items-start gap-5">
              <CampaignImage schoolId={schoolId} campaignId={detail.id} present={detail.hasCover} version={detail.coverVersion} alt="Capa da campanha" className="aspect-[16/9] w-full max-w-64 rounded-[var(--r-md)] border border-line" />
              {!ended && (
                <ImageButtons
                  what="capa da campanha"
                  hasImage={detail.hasCover}
                  disabled={busy !== null}
                  onUpload={async (file) => {
                    const result = await api.campaigns.setImage(schoolId, detail.id, file);
                    if (result.ok) {
                      changed(result.data, "Capa salva.");
                      return null;
                    }
                    if (result.error.status === 409) stale();
                    const text = describeCampaignError(result.error);
                    return text.general ?? Object.values(text.fields)[0] ?? "Não foi possível enviar a imagem.";
                  }}
                  onRemove={async () => {
                    const result = await api.campaigns.clearImage(schoolId, detail.id);
                    if (result.ok) changed(result.data, "Capa removida.");
                    else setProblem(describeCampaignError(result.error).general);
                  }}
                />
              )}
            </div>
          </section>

          <section aria-labelledby={`items-${detail.id}`}>
            <h2 id={`items-${detail.id}`} className="text-heading">
              Produtos
            </h2>
            <p className="mt-1 text-sub text-ink-2">
              A família escolhe quantos de cada e paga pelo Pix. O total é sempre calculado pelo servidor com os preços de hoje.
            </p>
            {detail.items.length === 0 ? (
              <p className="mt-4 rounded-[var(--r-md)] border border-line px-4 py-6 text-center text-sub text-ink-2">Nenhum produto ainda. Adicione o primeiro abaixo.</p>
            ) : (
              <ul aria-label="Produtos da campanha" className="mt-4 space-y-3">
                {detail.items.map((item) => (
                  <CampaignItemRow
                    key={`${item.id}|${detail.updatedAt}`}
                    schoolId={schoolId}
                    campaignId={detail.id}
                    campaignTitle={detail.title}
                    item={item}
                    editable={!ended}
                    onDetail={changed}
                    onProblem={setProblem}
                    onStale={stale}
                  />
                ))}
              </ul>
            )}
            {!ended && detail.items.length < MAX_ITEMS && <AddItem key={detail.items.length} schoolId={schoolId} campaignId={detail.id} onDetail={changed} onProblem={setProblem} onStale={stale} />}
          </section>
        </div>

        <section aria-labelledby={`preview-${detail.id}`} className="min-w-0">
          <h2 id={`preview-${detail.id}`} className="text-heading">
            Como a família vê
          </h2>
          <p className="mb-4 mt-1 text-sub text-ink-2">Os produtos que estão ligados, com o preço de hoje.</p>
          <CampaignPreview schoolId={schoolId} campaign={detail} />
        </section>
      </div>

      <Modal open={confirming !== null} onClose={() => busy === null && setConfirming(null)} label={confirming === "end" ? "Encerrar campanha" : "Pôr à venda"}>
        <div className="space-y-5 p-5 sm:p-8">
          <h2 className="text-title text-brand-800">{confirming === "end" ? "Encerrar esta campanha?" : "Pôr esta campanha à venda?"}</h2>
          <p className="text-body text-ink-2">
            {confirming === "end"
              ? "Encerrar é definitivo: nada mais é vendido e a campanha não muda mais. Os pedidos já feitos e o que entrou no caixa continuam."
              : "As famílias passam a ver a campanha na página da escola e podem fazer pedidos. Você ainda pode mudar preços e produtos depois."}
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <Button variant="plain" size="md" onClick={() => setConfirming(null)} disabled={busy !== null} className="rounded-full!">
              Voltar
            </Button>
            {confirming === "end" ? (
              <Button size="md" onClick={() => void run("end", () => api.campaigns.end(schoolId, detail.id), "Campanha encerrada.")} disabled={busy !== null} aria-busy={busy === "end"} className="rounded-full!">
                {busy === "end" ? "Encerrando…" : "Encerrar de vez"}
              </Button>
            ) : (
              <Button size="md" onClick={() => void run("activate", () => api.campaigns.activate(schoolId, detail.id), "Campanha à venda.")} disabled={busy !== null} aria-busy={busy === "activate"} className="rounded-full!">
                {busy === "activate" ? "Colocando…" : "Pôr à venda"}
              </Button>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}

interface SharedProps {
  schoolId: string;
  onDetail: (detail: CampaignDetail, message?: string) => void;
  onProblem: (text: string | null) => void;
  onStale: () => void;
}

function TextAndDates({ schoolId, detail, disabled, onDetail, onProblem, onStale }: SharedProps & { detail: CampaignDetail; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(detail.title);
  const [description, setDescription] = useState(detail.description ?? "");
  const [startsOn, setStartsOn] = useState(detail.startsOn ?? "");
  const [endsOn, setEndsOn] = useState(detail.endsOn ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const period = describePeriod(detail.startsOn, detail.endsOn);

  async function save() {
    if (busy) return;
    const problems: Record<string, string> = {};
    if (!title.trim()) problems.title = "Escreva o título da campanha.";
    if (startsOn && endsOn && startsOn > endsOn) problems.ends_on = "A data de fim não pode ser antes da data de início.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    onProblem(null);
    const result = await api.campaigns.update(schoolId, detail.id, {
      title: title.trim(),
      description: description.trim() || null,
      startsOn: startsOn || null,
      endsOn: endsOn || null,
    });
    setBusy(false);
    if (result.ok) return onDetail(result.data, "Campanha salva.");
    const text = describeCampaignError(result.error);
    setErrors(text.fields);
    onProblem(text.general);
    if (result.error.status === 409) onStale();
  }

  return (
    <section aria-labelledby={`text-${detail.id}`}>
      <h2 id={`text-${detail.id}`} className="text-heading">
        Texto e datas
      </h2>
      <dl className="mt-3 space-y-2 text-sub">
        <div>
          <dt className="text-ink-2">Título</dt>
          <dd className="text-[1.0625rem] font-semibold text-brand-800 [overflow-wrap:anywhere]">{detail.title}</dd>
        </div>
        <div>
          <dt className="text-ink-2">Texto para as famílias</dt>
          <dd className="whitespace-pre-line text-ink [overflow-wrap:anywhere]">{detail.description ?? "Sem texto."}</dd>
        </div>
        <div>
          <dt className="text-ink-2">À venda</dt>
          <dd className="text-ink">{period ?? "Sem datas: vale até a campanha ser encerrada."}</dd>
        </div>
      </dl>
      {!disabled && (
        <Button variant="secondary" size="md" onClick={() => setOpen(true)} className="mt-4 rounded-full!">
          Editar texto e datas
        </Button>
      )}
      <FormModal open={open && !disabled} title="Editar campanha" intro="O texto e as datas que as famílias veem na página da campanha." onClose={() => setOpen(false)} busy={busy}>
        <form
          method="post"
          noValidate
          aria-label="Texto e datas da campanha"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
          className="space-y-5"
        >
          <TextField label="Título" name="campaign-title" autoComplete="off" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
          <TextAreaField label="Texto para as famílias" name="campaign-description" optional rows={4} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label="Começa em" optional name="campaign-starts" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} error={errors.starts_on} />
            <TextField label="Termina em" optional name="campaign-ends" type="date" value={endsOn} onChange={(e) => setEndsOn(e.target.value)} hint="Depois desta data a campanha sai da página da escola." error={errors.ends_on} />
          </div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Salvar texto e datas" pendingLabel="Salvando…" pending={busy} />
        </form>
      </FormModal>
    </section>
  );
}

function AddItem({ schoolId, campaignId, onDetail, onProblem, onStale }: SharedProps & { campaignId: string }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [cents, setCents] = useState(0);
  const [limit, setLimit] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function add() {
    if (busy) return;
    const problems: Record<string, string> = {};
    if (!name.trim()) problems.name = "Escreva o nome do produto.";
    if (cents < MIN_PRICE_CENTS || cents > MAX_PRICE_CENTS) problems.price_cents = "O preço vai de R$ 1,00 a R$ 10.000,00.";
    const max = limit.trim() === "" ? null : Number(limit);
    if (max !== null && (!Number.isInteger(max) || max < 1 || max > 99)) problems.max_per_order = "O limite por pedido vai de 1 a 99.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    onProblem(null);
    const result = await api.campaigns.addItem(schoolId, campaignId, { name: name.trim(), description: description.trim() || undefined, priceCents: cents, maxPerOrder: max });
    setBusy(false);
    if (result.ok) return onDetail(result.data, "Produto adicionado.");
    const text = describeCampaignError(result.error);
    setErrors(text.fields);
    onProblem(text.general);
    if (result.error.status === 409) onStale();
  }

  return (
    <div className="mt-5">
      <Button variant="secondary" size="md" onClick={() => setOpen(true)} className="rounded-full!">
        Novo produto
      </Button>
      <FormModal open={open} title="Adicionar produto" intro="Nome, preço e, se quiser, um limite por pedido. A imagem você coloca depois, ao editar o produto." onClose={() => setOpen(false)} busy={busy}>
        <form
          method="post"
          noValidate
          aria-label="Adicionar produto"
          onSubmit={(event) => {
            event.preventDefault();
            void add();
          }}
          className="space-y-5"
        >
          <TextField label="Nome do produto" name="new-item-name" autoComplete="off" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
          <TextAreaField label="Descrição" name="new-item-description" optional rows={2} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Preço"
              name="new-item-price"
              prefix="R$"
              inputMode="numeric"
              autoComplete="off"
              placeholder="0,00"
              value={cents === 0 ? "" : formatBRLNumber(cents)}
              onChange={(e) => setCents(centsFromDigits(e.target.value))}
              error={errors.price_cents}
            />
            <TextField label="Limite por pedido" optional name="new-item-limit" inputMode="numeric" autoComplete="off" placeholder="Sem limite" value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, "").slice(0, 2))} error={errors.max_per_order} />
          </div>
          <FormButtons onCancel={() => setOpen(false)} submitLabel="Adicionar produto" pendingLabel="Adicionando…" pending={busy} />
        </form>
      </FormModal>
    </div>
  );
}
