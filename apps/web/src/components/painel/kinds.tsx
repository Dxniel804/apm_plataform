import type { ReactNode } from "react";
import { CashCoinIcon, Cart4Icon, CounterclockwiseIcon, ReplyAllIcon } from "@/components/ui/icons";
import type { MovementKind } from "@/lib/status";

/** Os 4 tipos do dominio sao DISTINTOS: cada um tem forma de icone, rotulo e cor proprios. */
export const KIND_META: Record<MovementKind, { icon: ReactNode; tile: string; definition: string; plural: string }> = {
  CONTRIBUTION: {
    icon: <CashCoinIcon size={22} />,
    tile: "bg-ok-soft text-ok",
    plural: "Contribuições",
    definition: "Entradas: o dinheiro que as famílias pagam à APM, em geral por Pix.",
  },
  EXPENSE: {
    icon: <Cart4Icon size={22} />,
    tile: "bg-neutral-soft text-ink",
    plural: "Despesas",
    definition: "Gastos da APM com fornecedores e serviços.",
  },
  REIMBURSEMENT: {
    icon: <ReplyAllIcon size={22} />,
    tile: "bg-info-soft text-info",
    plural: "Reembolsos",
    definition: "Devolução de dinheiro que um colaborador gastou do próprio bolso em nome da APM.",
  },
  REFUND: {
    icon: <CounterclockwiseIcon size={22} />,
    tile: "bg-warn-soft text-warn",
    plural: "Devoluções",
    definition: "Estorno de uma movimentação: o valor volta para quem pagou.",
  },
};
