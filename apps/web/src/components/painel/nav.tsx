import type { ReactNode } from "react";
import {
  BarChartIcon,
  BagIcon,
  CalendarCheckIcon,
  CashCoinIcon,
  Cart4Icon,
  ChatLeftTextIcon,
  CounterclockwiseIcon,
  ReplyAllIcon,
  SettingsIcon,
  BankIcon,
} from "@/components/ui/icons";
import { sectionHref } from "@/lib/painel-section";
import { areaHref, type Areas, type PainelArea } from "@/lib/permissions";
import type { MovementKind } from "@/lib/status";

export interface NavChild {
  kind: MovementKind;
  /** Quando o filho leva a outra area (ex.: "Despesas" abre a fila de despesas), a area dele. */
  area?: PainelArea;
  label: string;
  href: string;
  icon: ReactNode;
}

export interface NavItem {
  area: PainelArea;
  label: string;
  href: string;
  icon: ReactNode;
  /** "Lancamento do mes": os 4 tipos do extrato (so quem le o extrato). */
  children?: NavChild[];
}

/** Os 4 tipos do dominio, na ordem do menu do Figma. */
const KIND_NAV: Array<{ kind: MovementKind; label: string; icon: ReactNode }> = [
  { kind: "CONTRIBUTION", label: "Contribuições", icon: <CashCoinIcon size={20} /> },
  { kind: "EXPENSE", label: "Despesas", icon: <Cart4Icon size={20} /> },
  { kind: "REIMBURSEMENT", label: "Reembolsos", icon: <ReplyAllIcon size={20} /> },
  { kind: "REFUND", label: "Devoluções", icon: <CounterclockwiseIcon size={20} /> },
];

/**
 * Menu por perfil, a partir das permissoes da sessao (nunca de um papel fixo no cliente):
 * funcionario = "Minhas despesas" e "Minhas solicitacoes"; gestao = Dashboard, Lancamento do mes, Despesas,
 * Solicitacoes, Personalizacao (campanhas) e Fechamento;
 * viewer = Dashboard e Fechamento (leitura, sem o extrato).
 */
export function navFor(areas: Areas, period?: string, options: { statement?: boolean } = {}): NavItem[] {
  const items: NavItem[] = [];
  const hasExpenses = areas.manageExpenses || areas.myExpenses;
  // "Lancamentos do mes" ja traz "Despesas": nesse caso o item solto de Despesas sai do menu (nada duplicado).
  const expensesInGroup = areas.resumo && !!options.statement && hasExpenses;
  if (areas.resumo) {
    items.push({
      area: "resumo",
      label: "Dashboard",
      href: areaHref("resumo", { period }),
      icon: <BarChartIcon size={22} />,
      children: options.statement
        ? KIND_NAV.map((k) =>
            k.kind === "EXPENSE" && expensesInGroup
              ? { ...k, area: "despesas" as const, href: areaHref("despesas") }
              : { ...k, href: sectionHref(k.kind, period) },
          )
        : undefined,
    });
  }
  if (hasExpenses && !expensesInGroup) {
    items.push({
      area: "despesas",
      label: areas.manageExpenses ? "Despesas" : "Minhas despesas",
      href: areaHref("despesas"),
      icon: <Cart4Icon size={22} />,
    });
  }
  if (areas.requests) {
    items.push({
      area: "solicitacoes",
      label: areas.manageRequests ? "Solicitações" : "Minhas solicitações",
      href: areaHref("solicitacoes"),
      icon: <ChatLeftTextIcon size={22} />,
    });
  }
  if (areas.manageCampaigns) {
    items.push({
      area: "campanhas",
      label: "Campanhas",
      href: areaHref("campanhas"),
      icon: <BagIcon size={22} />,
    });
  }
  if (areas.fechamento) {
    items.push({
      area: "fechamento",
      label: "Fechamento",
      href: areaHref("fechamento", { period }),
      icon: <CalendarCheckIcon size={22} />,
    });
  }
  if (areas.manageReconciliation) {
    items.push({
      area: "conciliacao",
      label: "Conciliação",
      href: areaHref("conciliacao"),
      icon: <BankIcon size={22} />,
    });
  }
  // Para todos: a troca de senha mora aqui. As configuracoes da escola so aparecem para quem pode mexer.
  items.push({
    area: "configuracoes",
    label: "Configurações",
    href: areaHref("configuracoes"),
    icon: <SettingsIcon size={22} />,
  });
  return items;
}
