"use client";

import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore, type ReactNode } from "react";
import { ExpensesArea } from "@/components/despesas/ExpensesArea";
import { PasswordForm } from "@/components/conta/PasswordForm";
import { ClosingsArea } from "@/components/fechamento/ClosingsArea";
import { CampaignsArea } from "@/components/personalizacao/CampaignsArea";
import { RequestsArea } from "@/components/solicitacoes/RequestsArea";
import { BagIcon, BarChartIcon, BoxArrowInRightIcon, CalendarCheckIcon, Cart4Icon, ChatLeftTextIcon, KeyIcon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import type { Session } from "@/lib/api/types";
import { describeAuthError, isSessionLost } from "@/lib/auth-messages";
import { sectionHref, type PainelSection } from "@/lib/painel-section";
import { areaHref, areasFor, type PainelArea } from "@/lib/permissions";
import { ROLE_LABELS, membershipTitle } from "@/lib/roles";
import { ContextChooser } from "./ContextChooser";
import { KIND_META } from "./kinds";
import { navFor } from "./nav";
import { PainelData } from "./PainelData";
import { Sidebar } from "./Sidebar";
import { TenantSwitcher } from "./TenantSwitcher";

interface PainelShellProps {
  /** REAL: quem esta logado e onde atua (GET /auth/me, lido no servidor). */
  session: Session;
  /** Area do menu: resumo (padrao), despesas ou fechamento. */
  area?: PainelArea;
  /** Dentro do resumo: os lancamentos por tipo (?tipo=). */
  section?: PainelSection;
  /** Quem tem as duas funcoes de despesa escolhe a aba (?aba=minhas). */
  tab?: "minhas" | "fila";
  /** YYYY-MM da URL (?mes=); sem ele a API usa o mes corrente no fuso da escola. */
  period?: string;
}

/* Preferencia "barra lateral recolhida": conveniencia so deste navegador (localStorage), nunca estado de negocio. */
const COLLAPSED_KEY = "apm.sidebar.collapsed";
const collapsedListeners = new Set<() => void>();
const subscribeCollapsed = (listener: () => void) => {
  collapsedListeners.add(listener);
  return () => void collapsedListeners.delete(listener);
};
const readCollapsed = () => {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
};
const writeCollapsed = (value: boolean) => {
  try {
    window.localStorage.setItem(COLLAPSED_KEY, value ? "1" : "0");
  } catch {
    /* sem armazenamento (janela privada): a barra so nao lembra */
  }
  collapsedListeners.forEach((listener) => listener());
};

export function PainelShell({ session, area = "resumo", section = "resumo", tab = "fila", period }: PainelShellProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const collapsed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);

  async function selectMembership(membershipId: string) {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    const result = await api.auth.switchContext(membershipId);
    if (result.ok) {
      setMenuOpen(false);
      router.refresh(); // o servidor le /auth/me de novo, ja com o novo vinculo
    } else if (isSessionLost(result.error)) {
      router.replace("/login");
    } else {
      setProblem(describeAuthError(result.error, "context"));
    }
    setBusy(false);
  }

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    setProblem(null);
    const result = await api.auth.logout();
    if (result.ok) {
      router.replace("/login");
      router.refresh();
      return;
    }
    setProblem(describeAuthError(result.error, "logout"));
    setSigningOut(false);
  }

  const active = session.activeMembership;
  if (!active) {
    return (
      <ContextChooser
        session={session}
        busy={busy}
        signingOut={signingOut}
        problem={problem}
        onSelect={selectMembership}
        onSignOut={signOut}
      />
    );
  }

  const areas = areasFor(active.permissions);
  const navItems = navFor(areas, period, { statement: active.permissions.includes("statement:read") });
  const { title, icon } = titleFor(area, section, areas.manageExpenses, areas.manageRequests);
  // O painel e da ESCOLA do vinculo ativo (todo vinculo tem uma, ADR-020). O id vem da sessao; a API ainda
  // confere contra o contexto.
  const schoolId = active.school.id;

  const sidebar = (variant: "bar" | "drawer") => (
    <Sidebar
      items={navItems}
      area={area}
      section={section}
      collapsed={variant === "bar" && collapsed}
      onToggleCollapsed={() => writeCollapsed(!collapsed)}
      onClose={variant === "drawer" ? () => setMenuOpen(false) : undefined}
      switcher={
        <TenantSwitcher
          memberships={session.memberships}
          active={active}
          onSelect={selectMembership}
          busy={busy}
          iconOnly={variant === "bar" && collapsed}
          inline={variant === "drawer"}
        />
      }
      userName={session.user.fullName}
      roleLabel={ROLE_LABELS[active.role]}
      accountHref={areaHref("conta")}
      onSignOut={signOut}
      signingOut={signingOut}
    />
  );

  return (
    <div
      className={`min-h-dvh bg-bg lg:grid ${
        collapsed ? "lg:grid-cols-[5.5rem_minmax(0,1fr)]" : "lg:grid-cols-[clamp(16rem,21vw,19rem)_minmax(0,1fr)]"
      }`}
    >
      {/* barra lateral (desktop) */}
      <aside className="sticky top-0 hidden h-dvh bg-white lg:block">{sidebar("bar")}</aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-4 bg-bg px-5 pb-3 pt-4 sm:px-8 lg:static lg:px-10 lg:pb-5 lg:pt-8">
          <h1 className="flex min-w-0 items-center gap-3 text-[1.25rem] font-normal leading-tight tracking-normal text-ink-2 lg:text-[1.5rem]">
            <span aria-hidden="true" className="shrink-0 text-ink-2">
              {icon}
            </span>
            <span className="truncate">{title}</span>
          </h1>
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Abrir o menu"
            aria-haspopup="dialog"
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink-2 hover:bg-white/70 lg:hidden"
          >
            <BoxArrowInRightIcon size={26} />
          </button>
        </header>

        <main
          id="conteudo"
          tabIndex={-1}
          className="mx-3 mb-6 flex-1 rounded-[var(--r-lg)] bg-white p-5 outline-none sm:mx-5 sm:p-8 lg:mx-8 lg:mb-8 lg:p-10"
        >
          {/* No celular o menu fica numa gaveta: o contexto (escola, papel, quem esta conectado) precisa estar sempre a vista.
              No desktop isso ja esta na barra lateral. */}
          <p className="mb-5 text-foot leading-snug text-ink-3 lg:hidden">
            {membershipTitle(active)} · {ROLE_LABELS[active.role]}
            <span className="block">Conectado como {session.user.fullName}</span>
          </p>

          {problem && (
            <p role="alert" className="mb-5 rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">
              {problem}
            </p>
          )}

          {area === "conta" ? (
            <PasswordForm />
          ) : area === "despesas" ? (
            <ExpensesArea key={schoolId} schoolId={schoolId} userId={session.user.id} permissions={active.permissions} tab={tab} />
          ) : area === "solicitacoes" ? (
            <RequestsArea key={schoolId} schoolId={schoolId} userId={session.user.id} permissions={active.permissions} tab={tab} />
          ) : area === "personalizacao" ? (
            <CampaignsArea key={schoolId} schoolId={schoolId} permissions={active.permissions} />
          ) : area === "fechamento" ? (
            <ClosingsArea key={schoolId} schoolId={schoolId} permissions={active.permissions} />
          ) : (
            <PainelData
              // Trocar de vinculo troca de escola: o estado dos numeros recomeca do zero.
              key={schoolId}
              schoolId={schoolId}
              section={section}
              period={period}
              permissions={active.permissions}
              onPeriodChange={(next) => router.replace(sectionHref(section, next))}
            />
          )}
        </main>
      </div>

      {/* gaveta do menu (celular) */}
      <Modal open={menuOpen} onClose={() => setMenuOpen(false)} label="Menu do painel" placement="drawer">
        {sidebar("drawer")}
      </Modal>
    </div>
  );
}

/** Titulo e icone do cabecalho, por area e por tipo de lancamento. */
function titleFor(area: PainelArea, section: PainelSection, manageExpenses: boolean, manageRequests: boolean): { title: string; icon: ReactNode } {
  if (area === "conta") return { title: "Alterar senha", icon: <KeyIcon size={26} /> };
  if (area === "despesas") return { title: manageExpenses ? "Despesas" : "Minhas despesas", icon: <Cart4Icon size={26} /> };
  if (area === "solicitacoes") return { title: manageRequests ? "Solicitações" : "Minhas solicitações", icon: <ChatLeftTextIcon size={26} /> };
  if (area === "personalizacao") return { title: "Personalização", icon: <BagIcon size={26} /> };
  if (area === "fechamento") return { title: "Fechamento", icon: <CalendarCheckIcon size={26} /> };
  if (section === "resumo") return { title: "Dashboard", icon: <BarChartIcon size={26} /> };
  return { title: KIND_META[section].plural, icon: KIND_META[section].icon };
}
