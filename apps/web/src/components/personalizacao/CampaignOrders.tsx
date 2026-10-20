"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button, chipClass } from "@/components/ui/Button";
import { CheckboxField } from "@/components/ui/CheckboxField";
import { StatusPill } from "@/components/ui/StatusPill";
import { TextField } from "@/components/ui/TextField";
import { CampaignBuyers } from "./CampaignBuyers";
import { api } from "@/lib/api";
import type { ApiResult, CampaignOrder, CampaignOrderPage, OrderDeliveryStatus, OrderPaymentStatus } from "@/lib/api/types";
import { deliveryStatusView, describeCampaignError, paymentStatusView } from "@/lib/campaign-labels";
import { formatDateTime } from "@/lib/format";
import { formatBRL } from "@/lib/money";

const PAGE = 25;

const PAYMENT_FILTERS: Array<{ value: OrderPaymentStatus | undefined; label: string }> = [
  { value: undefined, label: "Todos" },
  { value: "PAID", label: "Aprovados" },
  { value: "PENDING", label: "Pendentes" },
  { value: "CANCELLED", label: "Cancelados" },
];
const DELIVERY_FILTERS: Array<{ value: OrderDeliveryStatus | undefined; label: string }> = [
  { value: undefined, label: "Todas as entregas" },
  { value: "PENDING", label: "A entregar" },
  { value: "DELIVERED", label: "Entregues" },
];

const reference = (code: number) => `APM-${String(code).padStart(6, "0")}`;

interface Props {
  schoolId: string;
  campaignId: string;
  /** Avisa o painel da campanha que as entregas mudaram (ele recarrega os numeros do resumo). */
  onChanged: () => void;
}

/**
 * Os pedidos de uma campanha: quem comprou, o que, o pagamento (Pendente, Aprovado, Cancelado) e a entrega. A gestao
 * marca a entrega, um a um ou em lote, so de pedido aprovado, e pode desfazer. Quem decide e a API.
 */
export function CampaignOrders(props: Props) {
  const [view, setView] = useState<"orders" | "buyers">("orders");
  const views = [
    { id: "orders", label: "Pedidos" },
    { id: "buyers", label: "Quem comprou" },
  ] as const;
  return (
    <div className="space-y-5">
      <div role="tablist" aria-label="O que ver" className="flex flex-wrap gap-2.5">
        {views.map((v) => (
          <button key={v.id} type="button" role="tab" aria-selected={view === v.id} onClick={() => setView(v.id)} className={chipClass(view === v.id)}>
            {v.label}
          </button>
        ))}
      </div>
      {view === "orders" ? <OrdersList {...props} /> : <CampaignBuyers schoolId={props.schoolId} campaignId={props.campaignId} />}
    </div>
  );
}

function OrdersList({ schoolId, campaignId, onChanged }: Props) {
  const [payment, setPayment] = useState<OrderPaymentStatus | undefined>(undefined);
  const [delivery, setDelivery] = useState<OrderDeliveryStatus | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [typed, setTyped] = useState("");
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const key = `${schoolId}|${campaignId}|${payment}|${delivery}|${search}|${offset}|${version}`;
  const [loaded, setLoaded] = useState<{ key: string; res: ApiResult<CampaignOrderPage> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void api.campaigns.orders(schoolId, campaignId, { payment, delivery, search, limit: PAGE, offset }).then((res) => {
      if (!cancelled) setLoaded({ key, res });
    });
    return () => {
      cancelled = true;
    };
  }, [schoolId, campaignId, payment, delivery, search, offset, key]);

  const res = loaded?.res ?? null;
  const page = res && res.ok ? res.data : null;
  const paidOnPage = page ? page.items.filter((order) => order.paymentStatus === "PAID") : [];

  function refilter(change: () => void) {
    change();
    setOffset(0);
    setSelected(new Set());
    setNotice(null);
    setProblem(null);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    refilter(() => setSearch(typed.trim()));
  }

  function toggle(orderId: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(orderId);
      else next.delete(orderId);
      return next;
    });
  }

  async function change(orderIds: string[], delivered: boolean) {
    if (busy || orderIds.length === 0) return;
    setBusy(true);
    setProblem(null);
    setNotice(null);
    const result = await api.campaigns.changeDelivery(schoolId, campaignId, orderIds, delivered);
    setBusy(false);
    if (!result.ok) return setProblem(describeCampaignError(result.error).general ?? "Não foi possível salvar a entrega. Tente de novo.");
    const { changed, skipped } = result.data;
    setNotice(
      changed === 0
        ? "Nada mudou: esses pedidos já estavam assim."
        : `${changed} ${changed === 1 ? "pedido" : "pedidos"} ${delivered ? "marcado como entregue" : "voltou para a entregar"}.${skipped > 0 ? ` ${skipped} não puderam mudar (só pedido aprovado tem entrega).` : ""}`,
    );
    setSelected(new Set());
    setVersion((n) => n + 1);
    onChanged();
  }

  const chosen = [...selected];
  const first = page && page.total > 0 ? page.offset + 1 : 0;
  const last = page ? page.offset + page.items.length : 0;

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <div role="group" aria-label="Filtrar por pagamento" className="flex flex-wrap gap-2.5">
          {PAYMENT_FILTERS.map((f) => (
            <button key={f.label} type="button" aria-pressed={payment === f.value} onClick={() => refilter(() => setPayment(f.value))} className={chipClass(payment === f.value)}>
              {f.label}
            </button>
          ))}
        </div>
        <div role="group" aria-label="Filtrar por entrega" className="flex flex-wrap gap-2.5">
          {DELIVERY_FILTERS.map((f) => (
            <button key={f.label} type="button" aria-pressed={delivery === f.value} onClick={() => refilter(() => setDelivery(f.value))} className={chipClass(delivery === f.value)}>
              {f.label}
            </button>
          ))}
        </div>
        <form method="post" role="search" aria-label="Buscar pedidos" onSubmit={submitSearch} className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1 basis-64">
            <TextField label="Buscar" name="order-search" autoComplete="off" maxLength={80} placeholder="Aluno, turma, responsável ou número do pedido" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </div>
          <Button type="submit" variant="secondary" size="md" className="min-h-[3.375rem] rounded-full!">
            Buscar
          </Button>
        </form>
      </div>

      <div aria-live="polite" className="space-y-2">
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

      {!res && (
        <div role="status" aria-busy="true" aria-live="polite">
          <span className="sr-only">Carregando os pedidos…</span>
          <div aria-hidden="true" className="skeleton h-24 w-full" />
        </div>
      )}
      {res && !res.ok && (
        <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
          {describeCampaignError(res.error).general ?? "Não foi possível carregar os pedidos."}
        </p>
      )}

      {page && page.items.length === 0 && (
        <div className="rounded-[var(--r-lg)] border border-line px-6 py-10 text-center">
          <h3 className="text-heading">Nenhum pedido aqui</h3>
          <p className="mx-auto mt-2 max-w-[48ch] text-body text-ink-2">
            {payment || delivery || search ? "Nenhum pedido combina com esse filtro. Tire um filtro para ver mais." : "Quando as famílias fizerem pedidos, eles aparecem aqui."}
          </p>
        </div>
      )}

      {page && page.items.length > 0 && (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-[var(--r-md)] bg-chip px-4 py-2">
            <CheckboxField
              label="Marcar todos os aprovados desta página"
              checked={paidOnPage.length > 0 && paidOnPage.every((order) => selected.has(order.orderId))}
              disabled={paidOnPage.length === 0}
              onChange={(e) => setSelected(e.target.checked ? new Set(paidOnPage.map((order) => order.orderId)) : new Set())}
              className="min-w-0 flex-1 basis-64"
            />
            <div className="flex flex-wrap gap-2">
              <Button size="md" onClick={() => void change(chosen, true)} disabled={busy || chosen.length === 0} className="rounded-full!">
                Marcar como entregue{chosen.length > 0 ? ` (${chosen.length})` : ""}
              </Button>
              <Button variant="secondary" size="md" onClick={() => void change(chosen, false)} disabled={busy || chosen.length === 0} className="rounded-full!">
                Desmarcar entrega
              </Button>
            </div>
          </div>

          <ul aria-label="Pedidos da campanha" className="space-y-3">
            {page.items.map((order) => (
              <OrderRow key={order.orderId} order={order} selected={selected.has(order.orderId)} busy={busy} onSelect={(on) => toggle(order.orderId, on)} onChange={(delivered) => void change([order.orderId], delivered)} />
            ))}
          </ul>

          <nav aria-label="Páginas de pedidos" className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sub text-ink-2">
              Mostrando {first} a {last} de {page.total}
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" size="md" disabled={page.offset === 0} onClick={() => { setOffset(Math.max(0, page.offset - PAGE)); setSelected(new Set()); }} className="rounded-full!">
                Anteriores
              </Button>
              <Button variant="secondary" size="md" disabled={last >= page.total} onClick={() => { setOffset(page.offset + PAGE); setSelected(new Set()); }} className="rounded-full!">
                Próximos
              </Button>
            </div>
          </nav>
        </>
      )}
    </div>
  );
}

function OrderRow({ order, selected, busy, onSelect, onChange }: { order: CampaignOrder; selected: boolean; busy: boolean; onSelect: (on: boolean) => void; onChange: (delivered: boolean) => void }) {
  const pay = paymentStatusView(order.paymentStatus);
  const delivery = order.deliveryStatus ? deliveryStatusView(order.deliveryStatus) : null;
  const who = [order.studentName, order.className].filter(Boolean).join(" · ");
  const code = reference(order.referenceCode);
  return (
    <li className="rounded-[var(--r-md)] border border-line p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        {order.paymentStatus === "PAID" ? (
          <input type="checkbox" aria-label={`Escolher o pedido ${code}`} checked={selected} onChange={(e) => onSelect(e.target.checked)} className="mt-1 size-6 shrink-0 cursor-pointer accent-[var(--brand-800)]" />
        ) : (
          <span aria-hidden="true" className="size-6 shrink-0" />
        )}
        <div className="min-w-0 flex-1 basis-56">
          <p className="text-[1.0625rem] font-semibold leading-snug text-brand-800">
            {code} <span className="font-normal text-ink-2">· {formatDateTime(order.createdAt)}</span>
          </p>
          <p className="mt-0.5 text-sub text-ink [overflow-wrap:anywhere]">
            {who || "Aluno e turma não informados"}
            {order.guardianName ? ` · responsável: ${order.guardianName}` : ""}
          </p>
          <p className="mt-1 text-sub text-ink-2 [overflow-wrap:anywhere]">{order.lines.map((line) => `${line.quantity} × ${line.itemName}`).join(" · ")}</p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <p className="text-[1.125rem] font-bold tabular-nums text-brand-800">{formatBRL(order.amountCents)}</p>
          <div className="flex flex-wrap gap-2">
            <StatusPill tone={pay.tone}>{pay.label}</StatusPill>
            {delivery && <StatusPill tone={delivery.tone}>{delivery.label}</StatusPill>}
          </div>
        </div>
      </div>
      {order.paymentStatus === "PAID" && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {order.deliveryStatus === "DELIVERED" ? (
            <Button variant="plain" size="md" disabled={busy} onClick={() => onChange(false)} aria-label={`Desfazer a entrega do pedido ${code}`} className="rounded-full!">
              Desfazer entrega
            </Button>
          ) : (
            <Button variant="secondary" size="md" disabled={busy} onClick={() => onChange(true)} aria-label={`Marcar o pedido ${code} como entregue`} className="rounded-full!">
              Marcar como entregue
            </Button>
          )}
          {order.deliveryChangedAt && order.deliveryStatus === "DELIVERED" && <span className="text-foot text-ink-2">Entregue em {formatDateTime(order.deliveryChangedAt)}</span>}
        </div>
      )}
    </li>
  );
}
