# ruff: noqa: E501
"""the Forklin Central ends a person's open sessions: one SECURITY DEFINER function (docs/adr-forklin-sso.md, section 9)

Revision ID: 0025_forklin_revocation
Revises: 0024_school_identity
Create Date: 2026-10-16

When the Central removes or suspends somebody's access, disables the person, changes the role or
switches the organization or the product off, it tells this product with a signed event and the
product must end that person's sessions at once. The event arrives with no session and no school
context, and row level security is forced, so (like the sign-in and the password recovery) this
needs one narrow function of apm_definer. The perimeter grows by ONE function, two column grants
and two policies:

* `revoke_forklin_sessions(central_user_id, central_org_id)` finds the person by the id of the
  Central, confirms they have an ACTIVE membership in the organization that carries that
  `central_org_id` (defence in depth: an unknown person, or one of another organization, changes
  nothing) and revokes every open session of theirs. It returns how many were revoked (0 for any
  other case) and never touches memberships, the status or the password of the person.
* `apm_definer` gets SELECT (user_id, revoked_at) and UPDATE (revoked_at, revoked_reason) on
  `sessions`, and two policies that show and change only the sessions of people who have a
  `central_user_id`; the update can only turn an open session into a revoked one.
* the sessions learn the reason `central_revoked`.

The application role gains nothing but EXECUTE on the function: it still cannot update the
sessions of other people.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025_forklin_revocation"
down_revision: str | None = "0024_school_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROM_THE_CENTRAL = "EXISTS (SELECT 1 FROM public.users u WHERE u.id = sessions.user_id AND u.central_user_id IS NOT NULL)"

REVOKE = """
CREATE FUNCTION public.revoke_forklin_sessions(p_central_user_id uuid, p_central_org_id uuid)
RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE
    usr uuid;
    revoked integer;
BEGIN
    IF p_central_user_id IS NULL OR p_central_org_id IS NULL THEN
        RETURN 0;
    END IF;
    SELECT u.id INTO usr FROM public.users u WHERE u.central_user_id = p_central_user_id;
    IF NOT FOUND THEN
        RETURN 0;
    END IF;
    -- Row level security shows the definer only ACTIVE memberships: a person who is not (or no
    -- longer) a member of that organization is a no-op, with nothing revealed.
    IF NOT EXISTS (
        SELECT 1 FROM public.memberships m
          JOIN public.organizations o ON o.id = m.organization_id
         WHERE m.user_id = usr AND o.central_org_id = p_central_org_id) THEN
        RETURN 0;
    END IF;
    UPDATE public.sessions s
       SET revoked_at = now(), revoked_reason = 'central_revoked'
     WHERE s.user_id = usr AND s.revoked_at IS NULL;
    GET DIAGNOSTICS revoked = ROW_COUNT;
    RETURN revoked;
END
$fn$
"""

REASONS = "'logout', 'rotated', 'password_changed', 'password_reset', 'membership_inactive', 'user_inactive'"


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE sessions DROP CONSTRAINT ck_sessions_revoked_reason_valid")
    op.execute(
        "ALTER TABLE sessions ADD CONSTRAINT ck_sessions_revoked_reason_valid CHECK "
        f"(revoked_reason IS NULL OR revoked_reason IN ({REASONS}, 'central_revoked'))"
    )
    op.execute("GRANT SELECT (user_id, revoked_at) ON sessions TO apm_definer")
    op.execute("GRANT UPDATE (revoked_at, revoked_reason) ON sessions TO apm_definer")
    op.execute(
        "CREATE POLICY sessions_definer_select ON sessions FOR SELECT TO apm_definer "
        f"USING ({FROM_THE_CENTRAL})"
    )
    # An open session of a person of the Central can only become a revoked one.
    op.execute(
        "CREATE POLICY sessions_definer_update ON sessions FOR UPDATE TO apm_definer "
        f"USING (revoked_at IS NULL AND {FROM_THE_CENTRAL}) "
        f"WITH CHECK (revoked_at IS NOT NULL AND revoked_reason = 'central_revoked' AND {FROM_THE_CENTRAL})"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(REVOKE)
    op.execute("REVOKE ALL ON FUNCTION public.revoke_forklin_sessions(uuid, uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.revoke_forklin_sessions(uuid, uuid) TO apm_app")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")


def downgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute("DROP FUNCTION IF EXISTS public.revoke_forklin_sessions(uuid, uuid)")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP POLICY IF EXISTS sessions_definer_update ON sessions")
    op.execute("DROP POLICY IF EXISTS sessions_definer_select ON sessions")
    op.execute("REVOKE UPDATE (revoked_at, revoked_reason) ON sessions FROM apm_definer")
    op.execute("REVOKE SELECT (user_id, revoked_at) ON sessions FROM apm_definer")
    # Rows with the new reason may exist and row level security hides them from the owner: the old
    # constraint comes back NOT VALID (it binds every new row; old rows are not rechecked).
    op.execute("ALTER TABLE sessions DROP CONSTRAINT ck_sessions_revoked_reason_valid")
    op.execute(
        "ALTER TABLE sessions ADD CONSTRAINT ck_sessions_revoked_reason_valid CHECK "
        f"(revoked_reason IS NULL OR revoked_reason IN ({REASONS})) NOT VALID"
    )
    op.execute("RESET ROLE")
