"use client";

import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { ApiStatusChip } from "@/components/status/ApiStatusChip";
import {
  BoxArrowInLeftIcon,
  BoxArrowInRightIcon,
  CashCoinIcon,
  ChevronDownThinIcon,
  ChevronUpThinIcon,
  KeyIcon,
  XLgIcon,
} from "@/components/ui/icons";
import { Wordmark } from "@/components/ui/Logo";
import type { PainelSection } from "@/lib/painel-section";
import type { PainelArea } from "@/lib/permissions";
import type { NavItem } from "./nav";

interface SidebarProps {
  items: NavItem[];
  area: PainelArea;
  section: PainelSection;
  /** So no desktop: a barra vira uma coluna de icones. */
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  /** So na gaveta do celular: fecha a gaveta (botao e cada link do menu). */
  onClose?: () => void;
  /** Seletor de organizacao/escola (TenantSwitcher). */
  switcher: ReactNode;
  userName: string;
  roleLabel: string;
  accountHref: string;
  onSignOut: () => void;
  signingOut: boolean;
}

const itemBase = "flex min-h-[3.25rem] w-full items-center gap-3 rounded-[1.125rem] px-4 text-left text-[1.0625rem] transition-colors";
const itemIdle = "text-[#363636] hover:bg-info-soft";
const itemCurrent = "bg-grad-brand font-medium text-white";

/**
 * Menu do painel (Figma "Gestao"): Dashboard, "Lancamento do mes" com os 4 tipos, Despesas e Fechamento;
 * embaixo o nome de quem esta logado e "Sair". Serve a barra fixa do desktop e a gaveta do celular.
 */
export function Sidebar({
  items,
  area,
  section,
  collapsed = false,
  onToggleCollapsed,
  onClose,
  switcher,
  userName,
  roleLabel,
  accountHref,
  onSignOut,
  signingOut,
}: SidebarProps) {
  const groupId = useId();
  const [groupOpen, setGroupOpen] = useState(area === "resumo");
  const label = (text: string) => <span className={collapsed ? "sr-only" : "truncate"}>{text}</span>;
  const layout = collapsed ? "justify-center px-0" : "";

  return (
    <div className="flex h-full min-h-0 flex-col gap-5 px-4 py-5">
      <div className={`flex items-center gap-2 ${collapsed ? "flex-col" : "justify-between"}`}>
        <Link href="/painel" onClick={onClose} className="inline-flex min-h-11 items-center rounded-lg px-1.5">
          {collapsed ? <Wordmark width={64} /> : <Wordmark width={112} />}
        </Link>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar o menu"
            className="inline-flex size-11 items-center justify-center rounded-full text-ink-2 hover:bg-info-soft"
          >
            <XLgIcon size={20} />
          </button>
        ) : (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expandir o menu" : "Recolher o menu"}
            aria-expanded={!collapsed}
            className="hidden size-11 items-center justify-center rounded-full text-ink-2 hover:bg-info-soft lg:inline-flex"
          >
            {collapsed ? <BoxArrowInRightIcon size={24} /> : <BoxArrowInLeftIcon size={24} />}
          </button>
        )}
      </div>

      {switcher}

      <nav aria-label="Seções do painel" className="min-h-0 flex-1 overflow-y-auto">
        <ul className="space-y-1.5">
          {items.map((item) => {
            const current = item.area === area && (item.area !== "resumo" || section === "resumo");
            const children = item.children;
            return (
              <li key={item.area}>
                <Link
                  href={item.href}
                  onClick={onClose}
                  aria-current={current ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  className={`${itemBase} ${layout} ${current ? itemCurrent : itemIdle}`}
                >
                  {item.icon}
                  {label(item.label)}
                </Link>

                {children && !collapsed && (
                  <div className="mt-1.5">
                    <button
                      type="button"
                      aria-expanded={groupOpen}
                      aria-controls={groupId}
                      onClick={() => setGroupOpen((v) => !v)}
                      className={`${itemBase} ${itemIdle} justify-between`}
                    >
                      <span className="flex min-w-0 items-center gap-3">
                        <CashCoinIcon size={22} />
                        <span className="truncate">Lançamento do mês</span>
                      </span>
                      {groupOpen ? <ChevronUpThinIcon size={18} /> : <ChevronDownThinIcon size={18} />}
                    </button>
                    {groupOpen && (
                      <ul id={groupId} className="mt-1 space-y-1 pl-4">
                        {children.map((child) => {
                          const childCurrent = area === "resumo" && section === child.kind;
                          return (
                            <li key={child.kind}>
                              <Link
                                href={child.href}
                                onClick={onClose}
                                aria-current={childCurrent ? "page" : undefined}
                                className={`${itemBase} min-h-12 ${childCurrent ? "bg-info-soft font-semibold text-brand-800" : itemIdle}`}
                              >
                                {child.icon}
                                <span className="truncate">{child.label}</span>
                              </Link>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                )}

                {/* Barra recolhida: os 4 tipos viram uma coluna de icones. */}
                {children && collapsed && (
                  <ul className="mt-1.5 space-y-1.5">
                    {children.map((child) => {
                      const childCurrent = area === "resumo" && section === child.kind;
                      return (
                        <li key={child.kind}>
                          <Link
                            href={child.href}
                            title={child.label}
                            aria-current={childCurrent ? "page" : undefined}
                            className={`${itemBase} justify-center px-0 ${childCurrent ? "bg-info-soft text-brand-800" : itemIdle}`}
                          >
                            {child.icon}
                            <span className="sr-only">{child.label}</span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      <div className={`space-y-3 border-t border-line pt-4 ${collapsed ? "text-center" : ""}`}>
        <div className={collapsed ? "sr-only" : "min-w-0 px-1"}>
          <p className="truncate text-body font-medium text-[#363636]">{userName}</p>
          <p className="truncate text-foot text-ink-3">{roleLabel}</p>
        </div>
        <Link
          href={accountHref}
          onClick={onClose}
          aria-current={area === "conta" ? "page" : undefined}
          title={collapsed ? "Alterar senha" : undefined}
          className={`${itemBase} min-h-12 ${layout} ${area === "conta" ? "bg-info-soft font-semibold text-brand-800" : itemIdle}`}
        >
          <KeyIcon size={20} />
          {label("Alterar senha")}
        </Link>
        <button
          type="button"
          onClick={onSignOut}
          disabled={signingOut}
          title={collapsed ? "Sair" : undefined}
          className={`${itemBase} min-h-12 ${layout} ${itemIdle} disabled:opacity-60`}
        >
          <BoxArrowInRightIcon size={22} />
          {label(signingOut ? "Saindo…" : "Sair")}
        </button>
        {!collapsed && <ApiStatusChip />}
      </div>
    </div>
  );
}
