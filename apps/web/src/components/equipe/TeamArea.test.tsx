import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { parseTeam } from "@/lib/api/team";
import type { Team } from "@/lib/api/types";
import { areasFor } from "@/lib/permissions";
import { TeamArea } from "./TeamArea";

const member = (id: string, name: string, role: string, extra: Record<string, unknown> = {}) => ({
  membership_id: `m-${id}`, user_id: `u-${id}`, full_name: name, email: `${id}@escola.test`, role, status: "active", is_you: false, can_manage: true, ...extra,
});
const TEAM: Team = parseTeam(
  {
    members: [member("eu", "Carla Gestão", "secretaria", { is_you: true, can_manage: false }), member("ana", "Ana Funcionária", "staff"), member("rui", "Rui Suspenso", "staff", { status: "suspended" })],
    invitable_roles: ["staff"],
    pending: [{ id: "i1", email: "novo@escola.test", role: "staff", expires_at: "2026-10-18T12:00:00Z", can_manage: true }],
  },
  200,
)!;
const ok = { ok: true, data: true } as const;

afterEach(() => vi.restoreAllMocks());

describe("Equipe", () => {
  it("so quem pode convidar ve a area (invitations:create)", () => {
    expect(areasFor(["invitations:create"]).manageTeam).toBe(true);
    expect(areasFor(["expenses:submit"]).manageTeam).toBe(false);
  });

  it("mostra as pessoas, os convites e so oferece o botao onde a API deixa", async () => {
    vi.spyOn(api.team, "list").mockResolvedValue({ ok: true, data: TEAM });
    render(<TeamArea />);

    const people = await screen.findByRole("list", { name: "Pessoas da escola" });
    expect(people).toHaveTextContent("Carla Gestão (você)");
    expect(within(people).queryByRole("button", { name: /Suspender o acesso de Carla/ })).not.toBeInTheDocument();
    expect(within(people).getByRole("button", { name: "Suspender o acesso de Ana Funcionária" })).toBeInTheDocument();
    expect(within(people).getByRole("button", { name: "Reativar o acesso de Rui Suspenso" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Convites esperando" })).toHaveTextContent("novo@escola.test");
  });

  it("adiciona um funcionario: nome, e-mail e cargo padrao 'funcionario'", async () => {
    vi.spyOn(api.team, "list").mockResolvedValue({ ok: true, data: TEAM });
    const create = vi.spyOn(api.team, "create").mockResolvedValue(ok);
    const user = userEvent.setup();
    render(<TeamArea />);

    await user.click(await screen.findByRole("button", { name: "Adicionar funcionário" }));
    const dialog = await screen.findByRole("dialog", { name: "Adicionar funcionário" });
    await user.click(within(dialog).getByRole("button", { name: "Enviar o convite" }));
    expect(within(dialog).getByText("Escreva o nome completo.")).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Nome completo"), "Maria Silva");
    await user.type(within(dialog).getByLabelText("E-mail"), "maria@escola.test");
    await user.click(within(dialog).getByRole("button", { name: "Enviar o convite" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith({ fullName: "Maria Silva", email: "maria@escola.test", role: "staff" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Convite enviado para maria@escola.test");
  });

  it("e-mail que ja esta na equipe vira uma frase clara", async () => {
    vi.spyOn(api.team, "list").mockResolvedValue({ ok: true, data: TEAM });
    vi.spyOn(api.team, "create").mockResolvedValue({ ok: false, error: { kind: "problem", status: 409, code: "already_member" } });
    const user = userEvent.setup();
    render(<TeamArea />);

    await user.click(await screen.findByRole("button", { name: "Adicionar funcionário" }));
    const dialog = await screen.findByRole("dialog", { name: "Adicionar funcionário" });
    await user.type(within(dialog).getByLabelText("Nome completo"), "Ana Funcionária");
    await user.type(within(dialog).getByLabelText("E-mail"), "ana@escola.test");
    await user.click(within(dialog).getByRole("button", { name: "Enviar o convite" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("já faz parte da equipe");
  });

  it("reenvia e cancela convites, suspende e reativa pessoas", async () => {
    vi.spyOn(api.team, "list").mockResolvedValue({ ok: true, data: TEAM });
    const resend = vi.spyOn(api.team, "resend").mockResolvedValue(ok);
    const cancel = vi.spyOn(api.team, "cancel").mockResolvedValue(ok);
    const suspend = vi.spyOn(api.team, "suspend").mockResolvedValue(ok);
    const activate = vi.spyOn(api.team, "activate").mockResolvedValue(ok);
    const user = userEvent.setup();
    render(<TeamArea />);

    await user.click(await screen.findByRole("button", { name: "Reenviar o convite para novo@escola.test" }));
    await user.click(await screen.findByRole("button", { name: "Cancelar o convite de novo@escola.test" }));
    await user.click(await screen.findByRole("button", { name: "Suspender o acesso de Ana Funcionária" }));
    await user.click(await screen.findByRole("button", { name: "Reativar o acesso de Rui Suspenso" }));

    expect(resend).toHaveBeenCalledWith("i1");
    expect(cancel).toHaveBeenCalledWith("i1");
    expect(suspend).toHaveBeenCalledWith("m-ana");
    expect(activate).toHaveBeenCalledWith("m-rui");
  });
});
