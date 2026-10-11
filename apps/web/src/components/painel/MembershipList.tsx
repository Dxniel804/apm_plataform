import { SchoolMonogram } from "@/components/portal/SchoolMonogram";
import { CheckIcon } from "@/components/ui/icons";
import type { Membership } from "@/lib/api/types";
import { ROLE_LABELS, membershipTitle } from "@/lib/roles";

interface MembershipListProps {
  memberships: Membership[];
  activeId: string | null;
  disabled?: boolean;
  onSelect: (membershipId: string) => void;
}

/**
 * Lista de vinculos (escola e papel) vindos da sessao, na ordem da API. Cada escola e um cliente, entao nao ha
 * agrupamento por organizacao. O cliente so devolve o id de um vinculo que a API listou; quem confere se ele e
 * mesmo da pessoa e o servidor.
 */
export function MembershipList({ memberships, activeId, disabled = false, onSelect }: MembershipListProps) {
  return (
    <ul aria-label="Escolas da sua conta" className="py-1">
      {memberships.map((membership) => {
        const selected = membership.membershipId === activeId;
        return (
          <li key={membership.membershipId}>
            <button
              type="button"
              aria-current={selected ? "true" : undefined}
              disabled={disabled}
              onClick={() => {
                if (!selected) onSelect(membership.membershipId);
              }}
              className="flex min-h-12 w-full items-center gap-3 rounded-[1rem] px-3 py-2 text-left hover:bg-info-soft disabled:opacity-60"
            >
              <SchoolMonogram name={membershipTitle(membership)} size={32} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sub font-medium text-ink">{membershipTitle(membership)}</span>
                <span className="block truncate text-foot text-ink-2">{ROLE_LABELS[membership.role]}</span>
              </span>
              {selected && <CheckIcon size={18} className="shrink-0 text-brand-800" strokeWidth={2.4} />}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
