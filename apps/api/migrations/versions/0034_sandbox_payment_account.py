# ruff: noqa: E501
"""the simulated payment account of a sandbox organization (docs/adr-ambiente-sandbox.md)

Revision ID: 0034_sandbox_payment_account
Revises: 0033_org_environment
Create Date: 2026-10-27

The link a school gives to the families only opens when the school has an ACTIVE payment account. An
organization in `sandbox` has no gateway (there is none yet) and does not need one: it gets a
SIMULATED account, and the fake bank pays its charges. This adds TWO functions of apm_definer:

* `school_has_active_account(school_id)`: the old policy `schools_definer_select_public` asked
  `payment_accounts` directly, and `payment_accounts` asks `schools` when a row is written: writing
  an account as apm_definer made Postgres refuse the loop ("infinite recursion in policy"). The policy
  now calls this function instead (same meaning, and the function reads `payment_accounts` on its
  own, where nothing loops).

* `sync_sandbox_payment_account(central_org_id)`: for an organization that came from the Central, in
  `sandbox`, makes sure its school has an ACTIVE account of the provider SANDBOX (creates it, or
  turns an old one back on) unless it already has another ACTIVE account; in `production` it turns
  the SANDBOX account OFF (INACTIVE), because the fake bank does not exist there. Idempotent; answers
  whether the school ends up with an ACTIVE account.

What the definer gets for it is narrow: it may INSERT only an ACTIVE SANDBOX account with the constant
shape below, and UPDATE only the status of a SANDBOX account. (That the organization is a sandbox
of the Central is checked by the function; a policy that asked for it would loop.) The application role
gets nothing new (only EXECUTE on the function), and `secret_ref` is the constant `env:SANDBOX_NONE`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034_sandbox_payment_account"
down_revision: str | None = "0033_org_environment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE_ACCOUNT_FN = """
CREATE FUNCTION public.school_has_active_account(p_school_id uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM public.payment_accounts a
         WHERE a.school_id = p_school_id AND a.status = 'ACTIVE')
$fn$
"""

SYNC = """
CREATE FUNCTION public.sync_sandbox_payment_account(p_central_org_id uuid)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE
    org uuid;
    env text;
    sch uuid;
    acc uuid;
BEGIN
    IF p_central_org_id IS NULL THEN
        RETURN false;
    END IF;
    SELECT o.id, o.environment INTO org, env
      FROM public.organizations o WHERE o.central_org_id = p_central_org_id;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    SELECT s.id INTO sch FROM public.schools s WHERE s.organization_id = org;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF env <> 'sandbox' THEN
        UPDATE public.payment_accounts a SET status = 'INACTIVE', updated_at = now()
         WHERE a.school_id = sch AND a.provider = 'SANDBOX' AND a.status = 'ACTIVE';
        RETURN false;
    END IF;
    IF EXISTS (SELECT 1 FROM public.payment_accounts a WHERE a.school_id = sch AND a.status = 'ACTIVE') THEN
        RETURN true;
    END IF;
    SELECT a.id INTO acc FROM public.payment_accounts a
     WHERE a.school_id = sch AND a.provider = 'SANDBOX' AND a.external_account_id = 'sandbox';
    IF FOUND THEN
        UPDATE public.payment_accounts a SET status = 'ACTIVE', updated_at = now() WHERE a.id = acc;
    ELSE
        INSERT INTO public.payment_accounts (organization_id, school_id, provider, external_account_id, status, secret_ref)
        VALUES (org, sch, 'SANDBOX', 'sandbox', 'ACTIVE', 'env:SANDBOX_NONE');
    END IF;
    RETURN true;
END
$fn$
"""

# The policies look only at the row itself: one that asked `organizations` whether the organization
# is a sandbox would loop (organizations -> schools -> payment_accounts -> organizations). That the
# organization comes from the Central and IS a sandbox is checked by the function, which is closed.


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("GRANT SELECT (external_account_id) ON payment_accounts TO apm_definer")
    op.execute(
        "GRANT INSERT (organization_id, school_id, provider, external_account_id, status, secret_ref) "
        "ON payment_accounts TO apm_definer"
    )
    op.execute("GRANT UPDATE (status, updated_at) ON payment_accounts TO apm_definer")
    op.execute(
        "CREATE POLICY payment_accounts_definer_sandbox_select ON payment_accounts FOR SELECT "
        "TO apm_definer USING (provider = 'SANDBOX')"
    )
    op.execute(
        "CREATE POLICY payment_accounts_definer_sandbox_insert ON payment_accounts FOR INSERT "
        "TO apm_definer WITH CHECK (provider = 'SANDBOX' AND status = 'ACTIVE' "
        "AND external_account_id = 'sandbox' AND secret_ref = 'env:SANDBOX_NONE')"
    )
    op.execute(
        "CREATE POLICY payment_accounts_definer_sandbox_update ON payment_accounts FOR UPDATE "
        "TO apm_definer USING (provider = 'SANDBOX') WITH CHECK (provider = 'SANDBOX')"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    for ddl, signature in (
        (ACTIVE_ACCOUNT_FN, "school_has_active_account(uuid)"),
        (SYNC, "sync_sandbox_payment_account(uuid)"),
    ):
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO apm_app")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    # The public policy now goes through the function (see above); same meaning as before.
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP POLICY schools_definer_select_public ON schools")
    op.execute(
        "CREATE POLICY schools_definer_select_public ON schools FOR SELECT TO apm_definer "
        "USING (public.school_has_active_account(id))"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP POLICY schools_definer_select_public ON schools")
    op.execute(
        "CREATE POLICY schools_definer_select_public ON schools FOR SELECT TO apm_definer "
        "USING (EXISTS (SELECT 1 FROM public.payment_accounts a "
        "WHERE a.school_id = schools.id AND a.status = 'ACTIVE'))"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute("DROP FUNCTION IF EXISTS public.sync_sandbox_payment_account(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.school_has_active_account(uuid)")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    for policy in ("sandbox_update", "sandbox_insert", "sandbox_select"):
        op.execute(f"DROP POLICY IF EXISTS payment_accounts_definer_{policy} ON payment_accounts")
    op.execute("REVOKE UPDATE (status, updated_at) ON payment_accounts FROM apm_definer")
    op.execute(
        "REVOKE INSERT (organization_id, school_id, provider, external_account_id, status, secret_ref) "
        "ON payment_accounts FROM apm_definer"
    )
    op.execute("REVOKE SELECT (external_account_id) ON payment_accounts FROM apm_definer")
    op.execute("RESET ROLE")
