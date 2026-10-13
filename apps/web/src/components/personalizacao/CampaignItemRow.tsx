"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { StatusPill } from "@/components/ui/StatusPill";
import { TextAreaField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiResult, CampaignDetail, CampaignItem } from "@/lib/api/types";
import { MAX_PRICE_CENTS, MIN_PRICE_CENTS, describeCampaignError } from "@/lib/campaign-labels";
import { centsFromDigits, formatBRL, formatBRLNumber } from "@/lib/money";
import { CampaignImage } from "./CampaignImage";
import { ImageButtons } from "./ImageButtons";

interface Props {
  schoolId: string;
  campaignId: string;
  campaignTitle: string;
  item: CampaignItem;
  /** Uma campanha encerrada nao muda mais. */
  editable: boolean;
  /** Entrega a campanha inteira que a API devolveu (o painel se atualiza). */
  onDetail: (detail: CampaignDetail, message?: string) => void;
  onProblem: (text: string | null) => void;
  /** Recarrega a campanha quando a API diz que ela mudou por baixo. */
  onStale: () => void;
}

/** Um produto da campanha: foto, nome, preco, limite por pedido, ligar/desligar e editar. */
export function CampaignItemRow({ schoolId, campaignId, campaignTitle, item, editable, onDetail, onProblem, onStale }: Props) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(item.name);
  const [description, setDescription] = useState(item.description ?? "");
  const [cents, setCents] = useState(item.priceCents);
  const [limit, setLimit] = useState(item.maxPerOrder === null ? "" : String(item.maxPerOrder));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  /** Faz a chamada; devolve null se deu certo, ou o texto do problema (que tambem vai para o painel). */
  async function run(call: () => Promise<ApiResult<CampaignDetail>>, message: string): Promise<string | null> {
    onProblem(null);
    const result = await call();
    if (result.ok) {
      onDetail(result.data, message);
      return null;
    }
    const text = describeCampaignError(result.error);
    setErrors(text.fields);
    const problem = text.general ?? Object.values(text.fields)[0] ?? "Não foi possível salvar. Tente de novo.";
    onProblem(problem);
    if (result.error.status === 409 || result.error.status === 404) onStale();
    return problem;
  }

  function startEditing() {
    setName(item.name);
    setDescription(item.description ?? "");
    setCents(item.priceCents);
    setLimit(item.maxPerOrder === null ? "" : String(item.maxPerOrder));
    setErrors({});
    setEditing(true);
  }

  async function save() {
    if (busy) return;
    const problems: Record<string, string> = {};
    if (!name.trim()) problems.name = "Escreva o nome do produto.";
    if (cents < MIN_PRICE_CENTS || cents > MAX_PRICE_CENTS) problems.price_cents = "O preço vai de R$ 1,00 a R$ 10.000,00.";
    const max = limit.trim() === "" ? null : Number(limit);
    if (max !== null && (!Number.isInteger(max) || max < 1 || max > 99)) problems.max_per_order = "O limite por pedido vai de 1 a 99.";
    setErrors(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    const problem = await run(
      () => api.campaigns.updateItem(schoolId, campaignId, item.id, { name: name.trim(), description: description.trim() || null, priceCents: cents, maxPerOrder: max }),
      "Produto salvo.",
    );
    setBusy(false);
    if (problem === null) setEditing(false);
  }

  async function toggle() {
    if (busy) return;
    setBusy(true);
    await run(() => api.campaigns.updateItem(schoolId, campaignId, item.id, { isActive: !item.isActive }), item.isActive ? "Produto tirado da venda." : "Produto voltou à venda.");
    setBusy(false);
  }

  return (
    <li className="rounded-[var(--r-md)] border border-line p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-x-5 gap-y-4">
        <CampaignImage
          schoolId={schoolId}
          campaignId={campaignId}
          itemId={item.id}
          present={item.hasImage}
          version={item.imageVersion}
          alt={`Imagem do produto ${item.name}`}
          className="size-20 shrink-0 rounded-[0.875rem] border border-line sm:size-24"
        />
        <div className="min-w-0 flex-1 basis-48">
          <p className="text-[1.0625rem] font-semibold leading-snug text-brand-800 [overflow-wrap:anywhere]">{item.name}</p>
          {item.description && <p className="mt-0.5 text-sub text-ink-2 [overflow-wrap:anywhere]">{item.description}</p>}
          <p className="mt-1.5 text-sub text-ink-2">
            <span className="font-bold text-brand-800">{formatBRL(item.priceCents)}</span>
            {item.maxPerOrder !== null ? ` · até ${item.maxPerOrder} por pedido` : " · sem limite por pedido"}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <StatusPill tone={item.isActive ? "success" : "neutral"}>{item.isActive ? "À venda" : "Fora da venda"}</StatusPill>
        </div>
      </div>

      {editable && !editing && (
        <div className="mt-4 flex flex-wrap gap-3">
          <Button variant="secondary" size="md" onClick={startEditing} aria-label={`Editar o produto ${item.name}`} className="rounded-full!">
            Editar
          </Button>
          <Button variant="plain" size="md" onClick={() => void toggle()} disabled={busy} aria-label={`${item.isActive ? "Tirar da venda" : "Voltar a vender"} o produto ${item.name}`} className="rounded-full!">
            {item.isActive ? "Tirar da venda" : "Voltar a vender"}
          </Button>
        </div>
      )}

      {editable && editing && (
        <form
          method="post"
          noValidate
          aria-label={`Editar o produto ${item.name}`}
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
          className="mt-5 space-y-4 rounded-[var(--r-md)] border border-line bg-[#f7f7f7] p-4 sm:p-5"
        >
          <TextField label="Nome do produto" name="item-name" autoComplete="off" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
          <TextAreaField label="Descrição" name="item-description" optional rows={2} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Preço"
              name="item-price"
              prefix="R$"
              inputMode="numeric"
              autoComplete="off"
              placeholder="0,00"
              value={cents === 0 ? "" : formatBRLNumber(cents)}
              onChange={(e) => setCents(centsFromDigits(e.target.value))}
              hint="Um preço novo vale para os próximos pedidos. Os que já foram feitos não mudam."
              error={errors.price_cents}
            />
            <TextField label="Limite por pedido" optional name="item-limit" inputMode="numeric" autoComplete="off" placeholder="Sem limite" value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, "").slice(0, 2))} error={errors.max_per_order} />
          </div>
          <ImageButtons
            what={`imagem do produto ${item.name}`}
            hasImage={item.hasImage}
            disabled={busy}
            onUpload={(file) => run(() => api.campaigns.setImage(schoolId, campaignId, file, item.id), "Imagem do produto salva.")}
            onRemove={async () => {
              await run(() => api.campaigns.clearImage(schoolId, campaignId, item.id), "Imagem removida.");
            }}
          />
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button type="submit" size="md" disabled={busy} aria-busy={busy} className="rounded-full!">
              {busy ? "Salvando…" : "Salvar produto"}
            </Button>
            <Button variant="plain" size="md" onClick={() => setEditing(false)} disabled={busy} className="rounded-full!">
              Cancelar
            </Button>
          </div>
          <p className="sr-only">Produto da campanha {campaignTitle}</p>
        </form>
      )}
    </li>
  );
}
