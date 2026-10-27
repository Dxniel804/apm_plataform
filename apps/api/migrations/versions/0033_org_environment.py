# ruff: noqa: E501
"""the environment of an organization (sandbox or production), told by the Forklin Central

Revision ID: 0033_org_environment
Revises: 0032_pdde_out_of_cash
Create Date: 2026-10-26

The Central decides, per organization, whether every product of it runs in demonstration (`sandbox`)
or for real (`production`). This product only RECORDS what the Central says:

* `organizations.environment`. The organizations that already exist are marked `production` (they
  already operate: nothing real becomes a demonstration); the default for a new one is `sandbox`.
* The application role could update EVERY column of `organizations` (a table level grant). It now
  updates only `name` and `updated_at`, so that no session of a school can change its own mode (nor
  `central_org_id`). Reading is unchanged.
* `set_forklin_environment(central_org_id, environment)`: the single way to change it, for an
  organization that came from the Central, to one of the two values. It is a function of apm_definer
  and the application role can only call it. It answers whether something changed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_org_environment"
down_revision: str | None = "0032_pdde_out_of_cash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SET_ENVIRONMENT = """
CREATE FUNCTION public.set_forklin_environment(p_central_org_id uuid, p_environment text)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE
    changed integer;
BEGIN
    IF p_central_org_id IS NULL OR p_environment IS NULL
       OR p_environment NOT IN ('sandbox', 'production') THEN
        RETURN false;
    END IF;
    UPDATE public.organizations o
       SET environment = p_environment, updated_at = now()
     WHERE o.central_org_id = p_central_org_id AND o.environment <> p_environment;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed > 0;
END
$fn$
"""


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE organizations ADD COLUMN environment text NOT NULL DEFAULT 'production'")
    op.execute("ALTER TABLE organizations ALTER COLUMN environment SET DEFAULT 'sandbox'")
    op.execute(
        "ALTER TABLE organizations ADD CONSTRAINT ck_organizations_environment_valid "
        "CHECK (environment IN ('sandbox', 'production'))"
    )
    op.execute("REVOKE UPDATE ON organizations FROM apm_app")
    op.execute("GRANT UPDATE (name, updated_at) ON organizations TO apm_app")

    op.execute("GRANT SELECT (environment) ON organizations TO apm_definer")
    op.execute("GRANT UPDATE (environment, updated_at) ON organizations TO apm_definer")
    op.execute(
        "CREATE POLICY organizations_definer_update ON organizations FOR UPDATE TO apm_definer "
        "USING (central_org_id IS NOT NULL) WITH CHECK (central_org_id IS NOT NULL)"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(SET_ENVIRONMENT)
    op.execute("REVOKE ALL ON FUNCTION public.set_forklin_environment(uuid, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.set_forklin_environment(uuid, text) TO apm_app")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")


def downgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute("DROP FUNCTION IF EXISTS public.set_forklin_environment(uuid, text)")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP POLICY IF EXISTS organizations_definer_update ON organizations")
    op.execute("REVOKE UPDATE (environment, updated_at) ON organizations FROM apm_definer")
    op.execute("REVOKE SELECT (environment) ON organizations FROM apm_definer")
    op.execute("REVOKE UPDATE (name, updated_at) ON organizations FROM apm_app")
    op.execute("GRANT UPDATE ON organizations TO apm_app")
    op.execute("ALTER TABLE organizations DROP CONSTRAINT ck_organizations_environment_valid")
    op.execute("ALTER TABLE organizations DROP COLUMN environment")
    op.execute("RESET ROLE")
