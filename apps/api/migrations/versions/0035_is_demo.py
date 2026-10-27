# ruff: noqa: E501
"""demonstration data (is_demo): marked when it is made in a sandbox, hidden in production

Revision ID: 0035_is_demo
Revises: 0034_sandbox_payment_account
Create Date: 2026-10-27

The rule, in one line: what is made while an organization of the Central is in `sandbox` is
DEMONSTRATION, and the database hides it from everybody once the organization is in `production`.

* `is_demo` (default false, so nothing that exists is ever demonstration) on the 24 tables that hold
  what people do: the ledger, the Pix, the expenses, the campaigns, the requests, the bank
  statements, the PDDE and the tax retentions. The settings of the school (categories, settings,
  payment and bank accounts, tax rules, PDDE entities) are NOT demonstration: they carry over.
* `set_is_demo()`: a BEFORE INSERT trigger on each of them sets `is_demo` from the organization
  (a Central organization in sandbox). Nobody has to remember to set it, and it cannot be unset.
* `hides_demo()` (apm_definer, STABLE): true when the organization of the session is a Central
  organization in `production`. One RESTRICTIVE policy per table (`<table>_hide_demo`) says
  `NOT is_demo OR NOT hides_demo()`: it is ANDed with the policies that already exist, so no query,
  report or export has to know about it. Organizations that are not from the Central (local
  development, tests) are never marked and never hidden. Going back to sandbox shows it again.
* The business keys that would let a hidden demonstration row block a real one are now unique only
  among real rows: the reference code of a transaction, the active closing of a month, the same
  bank statement and the same line, the same invoice key.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035_is_demo"
down_revision: str | None = "0034_sandbox_payment_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEMO_TABLES = (
    "financial_transactions",
    "contributions",
    "contribution_items",
    "contribution_fees",
    "pix_charges",
    "webhook_events",
    "refunds",
    "reimbursements",
    "expenses",
    "expense_attachments",
    "monthly_closings",
    "campaigns",
    "campaign_items",
    "campaign_deliveries",
    "staff_requests",
    "staff_request_attachments",
    "bank_statement_imports",
    "bank_statement_lines",
    "bank_line_resolutions",
    "balancete_balances",
    "pdde_classifications",
    "pdde_documents",
    "pdde_carryovers",
    "tax_retentions",
)

SET_IS_DEMO = """
CREATE FUNCTION public.set_is_demo()
RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $fn$
BEGIN
    NEW.is_demo := coalesce((
        SELECT o.central_org_id IS NOT NULL AND o.environment = 'sandbox'
          FROM public.organizations o WHERE o.id = NEW.organization_id), false);
    RETURN NEW;
END
$fn$
"""

# The next reference code of a school counts the REAL rows only (the partial index answers it), so a
# hidden demonstration row never moves the numbering of the real ones; a demonstration row, made in
# a sandbox where everything is visible, counts all of them.
REFERENCE_CODE = """
CREATE OR REPLACE FUNCTION public.ft_assign_reference_code()
RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $fn$
BEGIN
    PERFORM pg_advisory_xact_lock(7001, hashtext(NEW.school_id::text));
    IF NEW.is_demo THEN
        SELECT coalesce(max(f.reference_code), 0) + 1 INTO NEW.reference_code
        FROM public.financial_transactions f WHERE f.school_id = NEW.school_id;
    ELSE
        SELECT coalesce(max(f.reference_code), 0) + 1 INTO NEW.reference_code
        FROM public.financial_transactions f WHERE f.school_id = NEW.school_id AND NOT f.is_demo;
    END IF;
    RETURN NEW;
END
$fn$
"""

REFERENCE_CODE_BEFORE = """
CREATE OR REPLACE FUNCTION public.ft_assign_reference_code()
RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog
AS $fn$
BEGIN
    PERFORM pg_advisory_xact_lock(7001, hashtext(NEW.school_id::text));
    SELECT coalesce(max(f.reference_code), 0) + 1 INTO NEW.reference_code
    FROM public.financial_transactions f WHERE f.school_id = NEW.school_id;
    RETURN NEW;
END
$fn$
"""

HIDES_DEMO = """
CREATE FUNCTION public.hides_demo()
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
    SELECT coalesce((
        SELECT o.central_org_id IS NOT NULL AND o.environment = 'production'
          FROM public.organizations o WHERE o.id = public.app_org()), false)
$fn$
"""


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for table in DEMO_TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN is_demo boolean NOT NULL DEFAULT false")
    op.execute(SET_IS_DEMO)
    # A trigger function needs no EXECUTE at the moment it fires (only when the trigger is made).
    op.execute("REVOKE ALL ON FUNCTION public.set_is_demo() FROM PUBLIC")
    op.execute(REFERENCE_CODE)
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(HIDES_DEMO)
    op.execute("REVOKE ALL ON FUNCTION public.hides_demo() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.hides_demo() TO apm_app, apm_owner")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    for table in DEMO_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_10_is_demo BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.set_is_demo()"
        )
        op.execute(
            f"CREATE POLICY {table}_hide_demo ON {table} AS RESTRICTIVE FOR SELECT "
            "USING (NOT is_demo OR NOT (SELECT public.hides_demo()))"
        )

    # A hidden demonstration row must not block a real one.
    op.execute(
        "ALTER TABLE financial_transactions DROP CONSTRAINT uq_financial_transactions_school_id_reference_code"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_financial_transactions_school_id_reference_code "
        "ON financial_transactions (school_id, reference_code) WHERE NOT is_demo"
    )
    op.execute("DROP INDEX uq_monthly_closings_active_period")
    op.execute(
        "CREATE UNIQUE INDEX uq_monthly_closings_active_period "
        "ON monthly_closings (school_id, period_start) WHERE reopened_at IS NULL AND NOT is_demo"
    )
    op.execute(
        "ALTER TABLE bank_statement_imports DROP CONSTRAINT uq_bank_statement_imports_school_id_file_sha256"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_bank_statement_imports_school_id_file_sha256 "
        "ON bank_statement_imports (school_id, file_sha256) WHERE NOT is_demo"
    )
    op.execute(
        "ALTER TABLE bank_statement_lines DROP CONSTRAINT uq_bank_statement_lines_school_id_bank_account_id_bank_ref"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_bank_statement_lines_school_id_bank_account_id_bank_ref "
        "ON bank_statement_lines (school_id, bank_account_id, bank_ref) WHERE NOT is_demo"
    )
    op.execute("DROP INDEX uq_pdde_documents_school_id_access_key")
    op.execute(
        "CREATE UNIQUE INDEX uq_pdde_documents_school_id_access_key "
        "ON pdde_documents (school_id, access_key) "
        "WHERE access_key IS NOT NULL AND voided_at IS NULL AND NOT is_demo"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    # Demonstration rows may exist now: the old keys come back only if they still hold.
    op.execute("DROP INDEX uq_pdde_documents_school_id_access_key")
    op.execute(
        "CREATE UNIQUE INDEX uq_pdde_documents_school_id_access_key ON pdde_documents "
        "(school_id, access_key) WHERE access_key IS NOT NULL AND voided_at IS NULL"
    )
    op.execute("DROP INDEX uq_bank_statement_lines_school_id_bank_account_id_bank_ref")
    op.execute(
        "ALTER TABLE bank_statement_lines ADD CONSTRAINT "
        "uq_bank_statement_lines_school_id_bank_account_id_bank_ref "
        "UNIQUE (school_id, bank_account_id, bank_ref)"
    )
    op.execute("DROP INDEX uq_bank_statement_imports_school_id_file_sha256")
    op.execute(
        "ALTER TABLE bank_statement_imports ADD CONSTRAINT "
        "uq_bank_statement_imports_school_id_file_sha256 UNIQUE (school_id, file_sha256)"
    )
    op.execute("DROP INDEX uq_monthly_closings_active_period")
    op.execute(
        "CREATE UNIQUE INDEX uq_monthly_closings_active_period ON monthly_closings "
        "(school_id, period_start) WHERE reopened_at IS NULL"
    )
    op.execute("DROP INDEX uq_financial_transactions_school_id_reference_code")
    op.execute(
        "ALTER TABLE financial_transactions ADD CONSTRAINT "
        "uq_financial_transactions_school_id_reference_code UNIQUE (school_id, reference_code)"
    )
    for table in DEMO_TABLES:
        op.execute(f"DROP POLICY {table}_hide_demo ON {table}")
        op.execute(f"DROP TRIGGER {table}_10_is_demo ON {table}")
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute("DROP FUNCTION public.hides_demo()")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(REFERENCE_CODE_BEFORE)
    op.execute("DROP FUNCTION public.set_is_demo()")
    for table in DEMO_TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN is_demo")
    op.execute("RESET ROLE")
