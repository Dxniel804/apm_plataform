"""one school per account: the access of a network to its schools is gone (ADR-020)

Revision ID: 0010_one_school_per_account
Revises: 0009_expiry_job
Create Date: 2026-10-11

Each school is a separate customer. Until now an organization could hold several schools and a
membership with `school_id` NULL (role `organization_admin`) saw all of them. From here on:

* a school is the only school of its organization (`uq_schools_organization_id`), so the
  organization is just the account of the customer and an organization-wide context can only ever
  see that one school;
* every membership and every invitation names a school (`school_id NOT NULL`), and the role
  `organization_admin`, the only one that spanned schools, no longer exists;
* `org_statement_summary`, the consolidated statement of a network, is dropped.

The row level security predicates stay as they are: with one school per organization the scope
"this organization" and the scope "this school" select the same rows, so there is nothing to
tighten, and rewriting the policies of a dozen tables would only add risk.

Existing data. The migration refuses to run, with a message that says what is in the way, when an
organization holds more than one school or when a membership or an invitation is organization-wide.
Moving a school to another organization is not possible (the ledger is frozen), so a development
database that still has a network is recreated and seeded again. Like the migrations before it, the
check reads as the admin: with an admin that row level security hides the rows from, the NOT NULL
and the unique index below still refuse the data, only with a less friendly message.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_one_school_per_account"
down_revision: str | None = "0009_expiry_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = "'school_admin', 'treasurer', 'staff', 'viewer'"
OLD_ROLES = "'organization_admin', 'school_admin', 'treasurer', 'staff', 'viewer'"

SUMMARY_COLUMNS = """
    timezone text, opening_balance_cents bigint, contributions_in_cents bigint,
    other_in_cents bigint, refunds_in_cents bigint, total_in_cents bigint,
    expenses_out_cents bigint, reimbursements_out_cents bigint, total_out_cents bigint,
    closing_balance_cents bigint, pending_reimbursements_cents bigint,
    balance_after_pending_cents bigint, entries_count integer
"""

# The function 0007 created, for the downgrade (nothing else in the schema calls it).
ORG_STATEMENT_SUMMARY = f"""
CREATE FUNCTION public.org_statement_summary(p_org uuid, p_from date, p_to date)
RETURNS TABLE (school_id uuid, school_name text, {SUMMARY_COLUMNS})
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog AS $body$
    SELECT s.id, s.name, r.timezone, r.opening_balance_cents, r.contributions_in_cents,
           r.other_in_cents, r.refunds_in_cents, r.total_in_cents, r.expenses_out_cents,
           r.reimbursements_out_cents, r.total_out_cents, r.closing_balance_cents,
           r.pending_reimbursements_cents, r.balance_after_pending_cents, r.entries_count
    FROM public.schools s
    CROSS JOIN LATERAL public.statement_summary(s.id, p_from, p_to) r
    WHERE s.organization_id = p_org
    ORDER BY s.name, s.id
$body$
"""

PRECONDITION = """
DO $$
DECLARE
    crowded integer;
    wide_memberships integer;
    wide_invitations integer;
BEGIN
    SELECT count(*) INTO crowded FROM (
        SELECT 1 FROM public.schools GROUP BY organization_id HAVING count(*) > 1) AS t;
    SELECT count(*) INTO wide_memberships FROM public.memberships
     WHERE school_id IS NULL OR role = 'organization_admin';
    SELECT count(*) INTO wide_invitations FROM public.invitations
     WHERE school_id IS NULL OR role = 'organization_admin';
    IF crowded > 0 OR wide_memberships > 0 OR wide_invitations > 0 THEN
        RAISE EXCEPTION 'cannot end the network access: % organization(s) with more than one school, '
            '% organization-wide membership(s) and % organization-wide invitation(s). A school '
            'cannot move to another organization (the ledger is frozen): recreate the development '
            'database and seed it again (docs/tenancy.md).',
            crowded, wide_memberships, wide_invitations USING ERRCODE = 'check_violation';
    END IF;
END
$$
"""


def upgrade() -> None:
    op.execute(PRECONDITION)
    op.execute("SET LOCAL ROLE apm_owner")

    op.execute("ALTER TABLE memberships DROP CONSTRAINT ck_memberships_role_valid")
    op.execute(
        "ALTER TABLE memberships DROP CONSTRAINT ck_memberships_organization_admin_is_org_wide"
    )
    op.execute("DROP INDEX uq_memberships_user_org_wide")
    op.execute("ALTER TABLE memberships ALTER COLUMN school_id SET NOT NULL")
    op.execute(
        f"ALTER TABLE memberships ADD CONSTRAINT ck_memberships_role_valid "
        f"CHECK (role IN ({ROLES}))"
    )

    op.execute("ALTER TABLE invitations DROP CONSTRAINT ck_invitations_role_valid")
    op.execute(
        "ALTER TABLE invitations DROP CONSTRAINT ck_invitations_organization_admin_is_org_wide"
    )
    op.execute("ALTER TABLE invitations ALTER COLUMN school_id SET NOT NULL")
    op.execute(
        f"ALTER TABLE invitations ADD CONSTRAINT ck_invitations_role_valid "
        f"CHECK (role IN ({ROLES}))"
    )

    op.execute("CREATE UNIQUE INDEX uq_schools_organization_id ON schools (organization_id)")

    op.execute("DROP FUNCTION IF EXISTS public.org_statement_summary(uuid, date, date)")
    op.execute("RESET ROLE")


def downgrade() -> None:
    # The roles and the organization-wide rows that existed are not restored (there is no way to
    # know them): the schema goes back to what accepts them.
    op.execute("SET LOCAL ROLE apm_owner")

    op.execute(ORG_STATEMENT_SUMMARY)
    op.execute("REVOKE ALL ON FUNCTION public.org_statement_summary(uuid, date, date) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.org_statement_summary(uuid, date, date) TO apm_app"
    )

    op.execute("DROP INDEX IF EXISTS uq_schools_organization_id")

    op.execute("ALTER TABLE invitations DROP CONSTRAINT IF EXISTS ck_invitations_role_valid")
    op.execute("ALTER TABLE invitations ALTER COLUMN school_id DROP NOT NULL")
    op.execute(
        f"ALTER TABLE invitations ADD CONSTRAINT ck_invitations_role_valid "
        f"CHECK (role IN ({OLD_ROLES}))"
    )
    op.execute(
        "ALTER TABLE invitations ADD CONSTRAINT ck_invitations_organization_admin_is_org_wide "
        "CHECK (role <> 'organization_admin' OR school_id IS NULL)"
    )

    op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS ck_memberships_role_valid")
    op.execute("ALTER TABLE memberships ALTER COLUMN school_id DROP NOT NULL")
    op.execute(
        f"ALTER TABLE memberships ADD CONSTRAINT ck_memberships_role_valid "
        f"CHECK (role IN ({OLD_ROLES}))"
    )
    op.execute(
        "ALTER TABLE memberships ADD CONSTRAINT ck_memberships_organization_admin_is_org_wide "
        "CHECK (role <> 'organization_admin' OR school_id IS NULL)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_memberships_user_org_wide "
        "ON memberships (user_id, organization_id) WHERE school_id IS NULL"
    )
    op.execute("RESET ROLE")
