"use client";

import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore, type ReactNode } from "react";
import { ExpensesArea } from "@/components/despesas/ExpensesArea";
import { PasswordForm } from "@/components/conta/PasswordForm";
import { ClosingsArea } from "@/components/fechamento/ClosingsArea";
import { ReconciliationArea } from "@/components/conciliacao/ReconciliationArea";
import { SettingsArea } from "@/components/configuracoes/SettingsArea";
import { CampaignsArea } from "@/components/personalizacao/CampaignsArea";
import { RequestsArea } from "@/components/solicitacoes/RequestsArea";
import { BagIcon, BarChartIcon, BoxArrowInRightIcon, BankIcon, CalendarCheckIcon, Cart4Icon, ChatLeftTextIcon, SettingsIcon } from "@/components/ui/icons";
import { FormModal } from "@/components/ui/FormModal";
import { Modal } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import type { Session } from "@/lib/api/types";
import { describeAuthError, isSessionLost } from "@/lib/auth-messages";
import { sectionHref, type CampaignTab, type PainelSection } from "@/lib/painel-section";
import { areasFor, type PainelArea } from "@/lib/permissions";
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
  /** Na area das campanhas: a campanha aberta (/painel/campanhas/{id}) e a aba escolhida (?aba=). */
  campaignId?: string;
  campaignTab?: CampaignTab;
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

export function PainelShell({ session, area = "resumo", section = "resumo", tab = "fila", period, campaignId, campaignTab = "resumo" }: PainelShellProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  // "Alterar senha" e uma janela por cima do painel. O endereco antigo /painel/conta continua valendo: abre o resumo ja com a janela.
  const [passwordOpen, setPasswordOpen] = useState(area === "conta");
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
  // /painel/conta mostra o resumo por baixo da janela.
  const shownArea: PainelArea = area === "conta" ? "resumo" : area;
  const { title, icon } = titleFor(shownArea, section, areas.manageExpenses, areas.manageRequests);
  // O painel e da ESCOLA do vinculo ativo (todo vinculo tem uma, ADR-020). O id vem da sessao; a API ainda
  // confere contra o contexto.
  const schoolId = active.school.id;

  function closePassword() {
    setPasswordOpen(false);
    if (area === "conta") router.replace("/painel"); // o endereco volta ao do resumo
  }

  const sidebar = (variant: "bar" | "drawer") => (
    <Sidebar
      items={navItems}
      area={shownArea}
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
      onChangePassword={() => setPasswordOpen(true)}
      passwordOpen={passwordOpen}
      onSignOut={signOut}
      signingOut={signingOut}
    />
  );

  return (
    <div className="painel-grid min-h-dvh bg-bg" data-collapsed={collapsed ? "true" : "false"}>
      {/* barra lateral (desktop) */}
      <aside className="sticky top-0 hidden h-dvh bg-bg lg:block">{sidebar("bar")}</aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-4 bg-bg px-5 pb-3 pt-4 sm:px-8 lg:static lg:px-4 lg:pb-3 lg:pt-5">
          <h1 className="flex min-w-0 items-center gap-3 text-[1rem] font-medium leading-tight tracking-normal text-ink">
            <span aria-hidden="true" className="shrink-0 text-ink">
              {icon}
            </span>
            <span className="truncate">{title}</span>
          </h1>
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Abrir o menu"
            aria-haspopup="dialog"
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink-2 hover:bg-white/80 lg:hidden"
          >
            <BoxArrowInRightIcon size={20} />
          </button>
        </header>

        <main
          id="conteudo"
          tabIndex={-1}
          className="mx-3 mb-6 flex-1 rounded-[var(--r-xl)] bg-white p-5 outline-none sm:mx-5 sm:p-6 lg:mb-5 lg:ml-0 lg:mr-5 lg:p-6"
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

          {shownArea === "despesas" ? (
            <ExpensesArea key={schoolId} schoolId={schoolId} userId={session.user.id} permissions={active.permissions} tab={tab} />
          ) : shownArea === "solicitacoes" ? (
            <RequestsArea key={schoolId} schoolId={schoolId} userId={session.user.id} permissions={active.permissions} tab={tab} />
          ) : shownArea === "campanhas" ? (
            <CampaignsArea key={schoolId} schoolId={schoolId} permissions={active.permissions} campaignId={campaignId} tab={campaignTab} />
          ) : shownArea === "conciliacao" ? (
            <ReconciliationArea key={schoolId} schoolId={schoolId} permissions={active.permissions} />
          ) : shownArea === "configuracoes" ? (
            <SettingsArea key={schoolId} schoolId={schoolId} permissions={active.permissions} />
          ) : shownArea === "fechamento" ? (
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

      {passwordOpen && (
        <FormModal title="Alterar senha" intro="Ao trocar, as outras sessões abertas com a sua conta são encerradas. Você continua conectado neste navegador." onClose={closePassword}>
          <PasswordForm onClose={closePassword} />
        </FormModal>
      )}

      {/* gaveta do menu (celular) */}
      <Modal open={menuOpen} onClose={() => setMenuOpen(false)} label="Menu do painel" placement="drawer">
        {sidebar("drawer")}
      </Modal>
    </div>
  );
}

/** Titulo e icone do cabecalho, por area e por tipo de lancamento. */
function titleFor(area: PainelArea, section: PainelSection, manageExpenses: boolean, manageRequests: boolean): { title: string; icon: ReactNode } {
  if (area === "despesas") return { title: manageExpenses ? "Despesas" : "Minhas despesas", icon: <Cart4Icon size={20} /> };
  if (area === "solicitacoes") return { title: manageRequests ? "Solicitações" : "Minhas solicitações", icon: <ChatLeftTextIcon size={20} /> };
  if (area === "campanhas") return { title: "Campanhas", icon: <BagIcon size={20} /> };
  if (area === "fechamento") return { title: "Fechamento", icon: <CalendarCheckIcon size={20} /> };
  if (area === "conciliacao") return { title: "Conciliação", icon: <BankIcon size={20} /> };
  if (area === "configuracoes") return { title: "Configurações", icon: <SettingsIcon size={20} /> };
  if (section === "resumo") return { title: "Dashboard", icon: <BarChartIcon size={20} /> };
  return { title: KIND_META[section].plural, icon: KIND_META[section].icon };
}
