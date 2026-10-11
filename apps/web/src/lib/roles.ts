import type { Membership, Role } from "@/lib/api/types";

export const ROLE_LABELS: Record<Role, string> = {
  school_admin: "Administrador da escola",
  treasurer: "Tesouraria",
  staff: "Equipe",
  viewer: "Leitura",
};

/** Nome principal de um vinculo: a escola (cada escola e um cliente, ADR-020). */
export function membershipTitle(membership: Membership): string {
  return membership.school.name;
}
