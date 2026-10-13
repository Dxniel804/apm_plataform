"use client";

import Link from "next/link";
import type { Ref } from "react";
import { Button } from "@/components/ui/Button";
import { ImageIcon } from "@/components/ui/icons";
import { campaignCoverUrl, campaignItemImageUrl } from "@/lib/api/public";
import type { PublicCampaign } from "@/lib/api/types";
import { describePeriod } from "@/lib/campaign-labels";
import { formatBRL } from "@/lib/money";
import { StickyActions } from "./FlowChrome";

/** O mais que um produto aceita por pedido quando a gestao nao pos limite (a API recusa mais que 99). */
const MOST = 99;

interface Props {
  slug: string;
  campaign: PublicCampaign;
  quantities: Record<string, number>;
  /** Erro geral do carrinho (ex.: "Escolha pelo menos um produto."). */
  error: string | null;
  /** O que o servidor recusou, por produto. */
  lineErrors: Record<string, string>;
  headingRef: Ref<HTMLHeadingElement>;
  onChange: (itemId: string, quantity: number) => void;
  onContinue: () => void;
}

/**
 * O carrinho: os produtos da campanha, o preco de hoje e quanto de cada. O TOTAL aqui e so uma conta de tela,
 * para a familia saber; quem decide o valor e o servidor, com os precos dele, quando o pedido e criado.
 */
export function CampaignCartStep({ slug, campaign, quantities, error, lineErrors, headingRef, onChange, onContinue }: Props) {
  const total = campaign.items.reduce((sum, item) => sum + item.priceCents * (quantities[item.id] ?? 0), 0);
  const count = campaign.items.reduce((sum, item) => sum + (quantities[item.id] ?? 0), 0);
  const period = describePeriod(null, campaign.endsOn);

  return (
    <form
      method="post"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onContinue();
      }}
    >
      {campaign.hasCover && (
        // eslint-disable-next-line @next/next/no-img-element -- imagem publica da API (mesma origem), com tamanho e cache proprios
        <img src={campaignCoverUrl(slug, campaign.id, campaign.coverVersion)} alt={`Capa da campanha ${campaign.title}`} className="mb-6 aspect-[16/9] w-full rounded-[var(--r-lg)] object-cover" />
      )}
      <h2 ref={headingRef} tabIndex={-1} className="text-title outline-none">
        Escolha os produtos
      </h2>
      {campaign.description && <p className="mt-2 max-w-[60ch] whitespace-pre-line text-body text-ink-2 [overflow-wrap:anywhere]">{campaign.description}</p>}
      {period && <p className="mt-1 text-sub text-ink-3">À venda {period}.</p>}

      <ul aria-label="Produtos da campanha" className="mt-6 space-y-3.5">
        {campaign.items.map((item) => {
          const quantity = quantities[item.id] ?? 0;
          const limit = item.maxPerOrder ?? MOST;
          const problem = lineErrors[item.id];
          return (
            <li key={item.id} className={`rounded-ctl border bg-white p-4 sm:p-5 ${problem ? "border-bad" : "border-field-border"}`}>
              <div className="flex items-start gap-4">
                {item.hasImage ? (
                  // eslint-disable-next-line @next/next/no-img-element -- imagem publica da API (mesma origem)
                  <img src={campaignItemImageUrl(slug, campaign.id, item.id, item.imageVersion)} alt="" loading="lazy" className="size-20 shrink-0 rounded-[0.875rem] object-cover sm:size-24" />
                ) : (
                  <span aria-hidden="true" className="grid size-20 shrink-0 place-items-center rounded-[0.875rem] bg-info-soft text-brand-800 sm:size-24">
                    <ImageIcon size={28} />
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-[1.125rem] font-bold leading-snug text-brand-800 [overflow-wrap:anywhere] sm:text-[1.25rem]">{item.name}</p>
                  {item.description && <p className="mt-0.5 text-sub text-ink-2 [overflow-wrap:anywhere]">{item.description}</p>}
                  <p className="mt-1.5 text-body font-semibold tabular-nums text-ink">{formatBRL(item.priceCents)}</p>
                  {item.maxPerOrder !== null && <p className="text-foot text-ink-3">No máximo {item.maxPerOrder} por pedido.</p>}
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between gap-4">
                <div role="group" aria-label={`Quantidade de ${item.name}`} className="inline-flex items-center gap-1 rounded-full border border-field-border">
                  <button
                    type="button"
                    onClick={() => onChange(item.id, Math.max(0, quantity - 1))}
                    disabled={quantity === 0}
                    aria-label={`Tirar um ${item.name}`}
                    className="inline-flex size-12 items-center justify-center rounded-full text-[1.5rem] font-semibold text-brand-800 hover:bg-info-soft disabled:opacity-40"
                  >
                    <span aria-hidden="true">−</span>
                  </button>
                  <span aria-live="polite" className="min-w-10 text-center text-body font-bold tabular-nums text-ink">
                    <span className="sr-only">Quantidade: </span>
                    {quantity}
                  </span>
                  <button
                    type="button"
                    onClick={() => onChange(item.id, Math.min(limit, quantity + 1))}
                    disabled={quantity >= limit}
                    aria-label={`Adicionar um ${item.name}`}
                    className="inline-flex size-12 items-center justify-center rounded-full text-[1.5rem] font-semibold text-brand-800 hover:bg-info-soft disabled:opacity-40"
                  >
                    <span aria-hidden="true">+</span>
                  </button>
                </div>
                <p className="text-body font-bold tabular-nums text-brand-800">{quantity > 0 ? formatBRL(item.priceCents * quantity) : ""}</p>
              </div>
              {problem && (
                <p role="alert" className="mt-3 text-sub font-medium text-bad">
                  {problem}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div aria-live="polite">
        {error && (
          <p role="alert" className="mt-4 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
            {error}
          </p>
        )}
      </div>

      <StickyActions>
        <Link href={`/escola/${encodeURIComponent(slug)}`} className="inline-flex min-h-14 shrink-0 items-center justify-center rounded-ctl border border-field-border bg-white px-5 font-bold text-brand-800 hover:bg-info-soft sm:min-w-32">
          Voltar
        </Link>
        <div className="flex flex-1 items-center justify-end gap-4">
          <p className="text-right leading-tight" aria-live="polite">
            <span className="block text-foot text-ink-2">{count === 0 ? "Nenhum produto" : `${count} ${count === 1 ? "item" : "itens"}`}</span>
            <span className="block text-[1.25rem] font-bold tabular-nums text-brand-800">{formatBRL(total)}</span>
          </p>
          <Button type="submit" variant="solid" className="sm:min-w-44">
            Continuar
          </Button>
        </div>
      </StickyActions>
    </form>
  );
}
