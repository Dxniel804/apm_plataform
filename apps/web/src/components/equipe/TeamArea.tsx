"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FormButtons, FormModal } from "@/components/ui/FormModal";
import { StatusPill } from "@/components/ui/StatusPill";
import { SelectField, TextField } from "@/components/ui/TextField";
import { api } from "@/lib/api";
import type { ApiError, ApiResult, Role, Team } from "@/lib/api/types";
import { formatDateLong } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/roles";

const NETWORK = "Não foi possível falar com o servidor. Confira a conexão e tente de novo. Nada foi alterado.";

/** Os textos de erro da equipe (a API manda so o codigo). */
function describeError(error: ApiError, fallback = "Não foi possível concluir. Tente de novo."): string {
  if (error.kind === "network" || error.kind === "timeout") return NETWORK;
  if (error.status === 429) return "Muitos pedidos seguidos. Espere um minuto e tente de novo.";
  switch (error.code) {
    case "already_member":
      return "Esta pessoa já faz parte da equipe desta escola.";
    case "invitation_pending":
      return "Já existe um convite esperando esta pessoa. Use “Reenviar” na lista de convites.";
    case "permission_denied":
      return "O seu perfil não pode fazer isso.";
    case "not_found":
      return "Não encontramos esta pessoa. Atualize a página.";
    case "validation_error":
      return "Confira o nome e o e-mail informados.";
    default:
      return fallback;
  }
}

const STATUS: Record<string, { label: string; tone: "success" | "warning" | "neutral" }> = {
  active: { label: "Ativo", tone: "success" },
  suspended: { label: "Suspenso", tone: "warning" },
  invited: { label: "Convidado", tone: "neutral" },
};

/**
 * Os cargos que a tela oferece: so FUNCIONARIO e GESTAO (os dois da escola, mais o responsavel, que nao tem login).
 * "Administrador da escola" e "Leitura" existem no sistema mas nao sao escolhidos aqui. Cada pessoa so ve os que a
 * API diz que ela pode trazer (a gestao traz funcionarios; o administrador traz os dois).
 */
const OFFERED: Role[] = ["staff", "treasurer"];

/**
 * Equipe da escola: quem faz parte, quem foi convidado e ainda nao entrou, e o botao de trazer um funcionario.
 * Hoje a pessoa recebe um e-mail com um link para escolher a senha; no ecossistema Forklin o e-mail sera o do
 * App e ela entrara por SSO (docs/forklin-employees.md). O site so mostra o que a API devolve e decide nada.
 */
export function TeamArea() {
  const [version, setVersion] = useState(0);
  const [loaded, setLoaded] = useState<{ version: number; res: ApiResult<Team> } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.team.list().then((res) => {
      if (!cancelled) setLoaded({ version, res });
    });
    return () => {
      cancelled = true;
    };
  }, [version]);

  async function run(id: string, action: () => Promise<ApiResult<true>>, done: string) {
    if (busyId) return;
    setBusyId(id);
    setProblem(null);
    setNotice(null);
    const result = await action();
    setBusyId(null);
    if (!result.ok) return setProblem(describeError(result.error));
    setNotice(done);
    setVersion((n) => n + 1);
  }

  if (!loaded) {
    return (
      <div role="status" aria-busy="true">
        <span className="sr-only">Carregando a equipe…</span>
        <div aria-hidden="true" className="skeleton h-32 w-full" />
      </div>
    );
  }
  if (!loaded.res.ok) {
    return <p role="alert" className="text-sub font-medium text-bad">{describeError(loaded.res.error, "Não foi possível carregar a equipe.")}</p>;
  }
  const team = loaded.res.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-[62ch] text-body text-ink-2">
          Quem faz parte da equipe desta escola. Ao adicionar um funcionário, ele recebe um e-mail para escolher a senha e entrar.
        </p>
        <Button variant="secondary" size="md" onClick={() => setAdding(true)} className="rounded-full!">
          Adicionar funcionário
        </Button>
      </div>
      <div aria-live="polite">
        {notice && <p role="status" className="rounded-[var(--r-md)] bg-ok-soft px-4 py-3 text-sub font-medium text-ok">{notice}</p>}
        {problem && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{problem}</p>}
      </div>

      {team.pending.length > 0 && (
        <section aria-label="Convites esperando" className="rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
          <h2 className="mb-1 text-heading">Convites esperando</h2>
          <p className="mb-3 text-sub text-ink-2">A pessoa ainda não abriu o link do e-mail. O link vale por 72 horas.</p>
          <ul aria-label="Convites esperando" className="divide-y divide-line">
            {team.pending.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                <div className="min-w-0 flex-1 basis-56">
                  <p className="font-semibold text-brand-800 [overflow-wrap:anywhere]">{p.email}</p>
                  <p className="text-sub text-ink-2">
                    {ROLE_LABELS[p.role]} · vale até {formatDateLong(p.expiresAt)}
                  </p>
                </div>
                {p.canManage && (
                  <>
                    <Button variant="chip" size="md" disabled={busyId === p.id} aria-label={`Reenviar o convite para ${p.email}`} onClick={() => void run(p.id, () => api.team.resend(p.id), "Convite reenviado. O link anterior deixou de valer.")} className="rounded-full!">
                      Reenviar
                    </Button>
                    <Button variant="plain" size="md" disabled={busyId === p.id} aria-label={`Cancelar o convite de ${p.email}`} onClick={() => void run(p.id, () => api.team.cancel(p.id), "Convite cancelado.")} className="rounded-full!">
                      Cancelar
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Pessoas da escola" className="rounded-[var(--r-lg)] border border-line bg-white p-5 sm:p-7">
        <h2 className="mb-3 text-heading">Pessoas</h2>
        <ul aria-label="Pessoas da escola" className="divide-y divide-line">
          {team.members.map((m) => {
            const status = STATUS[m.status] ?? { label: m.status, tone: "neutral" as const };
            return (
              <li key={m.membershipId} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                <div className="min-w-0 flex-1 basis-56">
                  <p className="font-semibold text-brand-800 [overflow-wrap:anywhere]">
                    {m.fullName}
                    {m.isYou ? " (você)" : ""}
                  </p>
                  <p className="text-sub text-ink-2 [overflow-wrap:anywhere]">
                    {m.email} · {ROLE_LABELS[m.role]}
                  </p>
                </div>
                <StatusPill tone={status.tone}>{status.label}</StatusPill>
                {m.canManage && m.status === "active" && (
                  <Button variant="plain" size="md" disabled={busyId === m.membershipId} aria-label={`Suspender o acesso de ${m.fullName}`} onClick={() => void run(m.membershipId, () => api.team.suspend(m.membershipId), "Acesso suspenso. A pessoa sai do sistema no próximo clique.")} className="rounded-full!">
                    Suspender
                  </Button>
                )}
                {m.canManage && m.status === "suspended" && (
                  <Button variant="chip" size="md" disabled={busyId === m.membershipId} aria-label={`Reativar o acesso de ${m.fullName}`} onClick={() => void run(m.membershipId, () => api.team.activate(m.membershipId), "Acesso reativado.")} className="rounded-full!">
                    Reativar
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {adding && (
        <AddEmployee
          choices={OFFERED.filter((r) => team.invitableRoles.includes(r))}
          onClose={() => setAdding(false)}
          onDone={(email) => {
            setAdding(false);
            setProblem(null);
            setNotice(`Convite enviado para ${email}. A pessoa recebe um e-mail para escolher a senha.`);
            setVersion((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}

function AddEmployee({ choices, onClose, onDone }: { choices: Role[]; onClose: () => void; onDone: (email: string) => void }) {
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const [role, setRole] = useState<Role>(choices[0] ?? "staff");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ name?: string; email?: string }>({});
  const [general, setGeneral] = useState<string | null>(null);

  async function save() {
    if (busy) return;
    const fullName = nameRef.current?.value.trim() ?? "";
    const email = emailRef.current?.value.trim() ?? "";
    const problems: { name?: string; email?: string } = {};
    if (fullName.length < 2) problems.name = "Escreva o nome completo.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) problems.email = "Escreva um e-mail válido.";
    setErrors(problems);
    setGeneral(null);
    if (problems.name) return nameRef.current?.focus();
    if (problems.email) return emailRef.current?.focus();
    setBusy(true);
    const result = await api.team.create({ fullName, email, role });
    setBusy(false);
    if (!result.ok) return setGeneral(describeError(result.error, "Não foi possível enviar o convite."));
    onDone(email);
  }

  return (
    <FormModal open title="Adicionar funcionário" intro="A pessoa recebe um e-mail com um link para escolher a senha. O link vale por 72 horas." onClose={onClose} busy={busy}>
      <form method="post" noValidate aria-label="Adicionar funcionário" onSubmit={(e) => { e.preventDefault(); void save(); }} className="space-y-5">
        <TextField label="Nome completo" name="employee-name" autoComplete="off" maxLength={200} inputRef={nameRef} error={errors.name} />
        <TextField label="E-mail" name="employee-email" type="email" inputMode="email" autoComplete="off" spellCheck={false} autoCapitalize="none" inputRef={emailRef} error={errors.email} />
        {choices.length > 1 && (
          <SelectField id="employee-role" label="Cargo" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {choices.map((r) => (
              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
            ))}
          </SelectField>
        )}
        <div aria-live="polite">{general && <p role="alert" className="rounded-[var(--r-md)] bg-bad-soft px-4 py-3 text-sub font-medium text-bad">{general}</p>}</div>
        <FormButtons onCancel={onClose} submitLabel="Enviar o convite" pendingLabel="Enviando…" pending={busy} />
      </form>
    </FormModal>
  );
}
