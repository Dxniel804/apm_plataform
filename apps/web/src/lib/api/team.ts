import { apiGet, apiSend, type RequestOptions, type SendOptions } from "./client";
import { ROLES, type ApiResult, type EmployeeInput, type PendingInvitation, type Role, type Team, type TeamMember } from "./types";

/**
 * A equipe da escola (/api/v1/employees). Hoje a gestao traz a pessoa por um convite por e-mail; quando a
 * plataforma entrar no ecossistema Forklin, o e-mail sera o do App e a pessoa entrara por SSO
 * (docs/forklin-employees.md). As telas e estas chamadas ficam.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
const str = (v: unknown): string | null => (typeof v === "string" && v.length > 0 ? v : null);
const role = (v: unknown): Role | null => (typeof v === "string" && (ROLES as readonly string[]).includes(v) ? (v as Role) : null);

function parseMember(v: unknown): TeamMember | null {
  if (!isRecord(v)) return null;
  const membershipId = str(v.membership_id);
  const userId = str(v.user_id);
  const fullName = str(v.full_name);
  const email = str(v.email);
  const r = role(v.role);
  const status = str(v.status);
  if (!membershipId || !userId || !fullName || !email || !r || !status || typeof v.is_you !== "boolean" || typeof v.can_manage !== "boolean") return null;
  return { membershipId, userId, fullName, email, role: r, status, isYou: v.is_you, canManage: v.can_manage };
}

function parsePending(v: unknown): PendingInvitation | null {
  if (!isRecord(v)) return null;
  const id = str(v.id);
  const email = str(v.email);
  const r = role(v.role);
  const expiresAt = str(v.expires_at);
  if (!id || !email || !r || !expiresAt || typeof v.can_manage !== "boolean") return null;
  return { id, email, role: r, expiresAt, canManage: v.can_manage };
}

export function parseTeam(body: unknown, status: number): Team | null {
  if (status !== 200 || !isRecord(body) || !Array.isArray(body.members) || !Array.isArray(body.pending)) return null;
  const members = body.members.map(parseMember);
  const pending = body.pending.map(parsePending);
  if (members.some((m) => m === null) || pending.some((p) => p === null)) return null;
  return { members: members as TeamMember[], pending: pending as PendingInvitation[] };
}

const BASE = "/api/v1/employees";
const created = (_b: unknown, status: number) => (status === 201 ? (true as const) : null);
const noContent = (_b: unknown, status: number) => (status === 204 ? (true as const) : null);

export function getTeam(options?: RequestOptions): Promise<ApiResult<Team>> {
  return apiGet(BASE, parseTeam, options);
}

/** POST /employees: a API manda o e-mail com o link para a pessoa escolher a senha. */
export function createEmployee(input: EmployeeInput, options?: SendOptions): Promise<ApiResult<true>> {
  return apiSend("POST", BASE, { full_name: input.fullName.trim(), email: input.email.trim(), ...(input.role ? { role: input.role } : {}) }, created, options);
}

export function resendInvitation(invitationId: string, options?: SendOptions): Promise<ApiResult<true>> {
  return apiSend("POST", `${BASE}/invitations/${encodeURIComponent(invitationId)}/resend`, undefined, created, options);
}

export function cancelInvitation(invitationId: string, options?: SendOptions): Promise<ApiResult<true>> {
  return apiSend("DELETE", `${BASE}/invitations/${encodeURIComponent(invitationId)}`, undefined, noContent, options);
}

export function suspendMember(membershipId: string, options?: SendOptions): Promise<ApiResult<true>> {
  return apiSend("POST", `${BASE}/${encodeURIComponent(membershipId)}/suspend`, undefined, noContent, options);
}

export function activateMember(membershipId: string, options?: SendOptions): Promise<ApiResult<true>> {
  return apiSend("POST", `${BASE}/${encodeURIComponent(membershipId)}/activate`, undefined, noContent, options);
}
