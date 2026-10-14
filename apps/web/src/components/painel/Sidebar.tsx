"use client";

import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { ApiStatusChip } from "@/components/status/ApiStatusChip";
import {
  ArrowLeftRightIcon,
  ArrowLeftToLineIcon,
  BoxArrowInRightIcon,
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
  /** Abre a janela "Alterar senha" (a gaveta do celular fecha antes). */
  onChangePassword: () => void;
  /** A janela esta aberta: o item do menu fica marcado. */
  passwordOpen: boolean;
  onSignOut: () => void;
  signingOut: boolean;
}

const itemBase = "flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-[0.9375rem] font-medium transition-colors";
const itemIdle = "text-ink hover:bg-white/80";
const itemCurrent = "bg-brand-200 font-semibold text-brand-800";

/**
 * Menu do painel (visual Paper v2): Dashboard, "Lancamentos do mes" com os 4 tipos (Despesas e um deles), Solicitacoes,
 * Personalizacao e Fechamento;
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
  onChangePassword,
  passwordOpen,
  onSignOut,
  signingOut,
}: SidebarProps) {
  const groupId = useId();
  const hasGroup = items.some((item) => item.children);
  const [groupOpen, setGroupOpen] = useState(area === "resumo" || (hasGroup && area === "despesas"));
  const label = (text: string) => <span className={collapsed ? "sr-only" : "truncate"}>{text}</span>;
  const layout = collapsed ? "justify-center px-0" : "";

  return (
    <div className="flex h-full min-h-0 flex-col gap-5 px-3.5 py-5">
      <div className={`flex items-center gap-2 ${collapsed ? "flex-col" : "justify-between"}`}>
        <Link href="/painel" onClick={onClose} className="inline-flex min-h-11 items-center rounded-lg px-1.5">
          {collapsed ? <Wordmark width={64} /> : <Wordmark width={104} />}
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
            className="hidden size-11 items-center justify-center rounded-full text-ink-2 hover:bg-white/80 lg:inline-flex"
          >
            {collapsed ? <BoxArrowInRightIcon size={22} /> : <ArrowLeftToLineIcon size={20} />}
          </button>
        )}
      </div>

      {switcher}

      <nav aria-label="Seções do painel" className="min-h-0 flex-1 overflow-y-auto">
        <ul className="space-y-1">
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
                  <div className="mt-1">
                    <button
                      type="button"
                      aria-expanded={groupOpen}
                      aria-controls={groupId}
                      onClick={() => setGroupOpen((v) => !v)}
                      className={`${itemBase} ${itemIdle} justify-between`}
                    >
                      <span className="flex min-w-0 items-center gap-3">
                        <ArrowLeftRightIcon size={22} />
                        <span className="truncate">Lançamentos do mês</span>
                      </span>
                      {groupOpen ? <ChevronUpThinIcon size={16} /> : <ChevronDownThinIcon size={16} />}
                    </button>
                    {groupOpen && (
                      <ul id={groupId} className="mt-0.5 space-y-0.5 border-b border-line-strong pb-2 pl-4">
                        {children.map((child) => {
                          const childCurrent = child.area ? area === child.area : area === "resumo" && section === child.kind;
                          return (
                            <li key={child.kind}>
                              <Link
                                href={child.href}
                                onClick={onClose}
                                aria-current={childCurrent ? "page" : undefined}
                                className={`${itemBase} min-h-10 pl-4 text-sub font-normal ${childCurrent ? itemCurrent : itemIdle}`}
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
                      const childCurrent = child.area ? area === child.area : area === "resumo" && section === child.kind;
                      return (
                        <li key={child.kind}>
                          <Link
                            href={child.href}
                            title={child.label}
                            aria-current={childCurrent ? "page" : undefined}
                            className={`${itemBase} justify-center px-0 ${childCurrent ? itemCurrent : itemIdle}`}
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

      <div className={`space-y-1 border-t border-line-strong pt-4 ${collapsed ? "text-center" : ""}`}>
        <div className={collapsed ? "sr-only" : "flex min-w-0 items-center gap-3 px-2 pb-2"}>
          <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-800 text-sub font-semibold text-white">
            {userName.trim().charAt(0).toUpperCase()}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sub font-medium text-ink">{userName}</span>
            <span className="block truncate text-[0.75rem] text-ink-3">{roleLabel}</span>
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            onClose?.();
            onChangePassword();
          }}
          aria-haspopup="dialog"
          aria-expanded={passwordOpen}
          title={collapsed ? "Alterar senha" : undefined}
          className={`${itemBase} ${layout} ${itemIdle}`}
        >
          <KeyIcon size={20} />
          {label("Alterar senha")}
        </button>
        <button
          type="button"
          onClick={onSignOut}
          disabled={signingOut}
          title={collapsed ? "Sair" : undefined}
          className={`${itemBase} ${layout} ${itemIdle} disabled:opacity-60`}
        >
          <BoxArrowInRightIcon size={20} />
          {label(signingOut ? "Saindo…" : "Sair")}
        </button>
        {!collapsed && <ApiStatusChip />}
      </div>
    </div>
  );
}
