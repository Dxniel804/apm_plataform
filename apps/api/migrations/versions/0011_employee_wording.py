"""wording: "Reembolso de professor" becomes "Reembolso de funcionário"

Revision ID: 0011_employee_wording
Revises: 0010_one_school_per_account
Create Date: 2026-10-11

The staff of a school are called "funcionário", not "professor". The key of the category
(`teacher_reimbursement`) is stable and does not change; only the name the school sees does, in the
schools that already exist and in the default set the trigger of a new school installs.

The rows are renamed as the admin, like the backfill of 0007: with an admin that row level security
hides the categories from, nothing is renamed and the schools keep the old name until somebody
renames the category (the name is editable), which is harmless.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_employee_wording"
down_revision: str | None = "0010_one_school_per_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "Reembolso de professor"
NEW = "Reembolso de funcionário"
HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"

# The default purposes of a school (the same list as 0007, with the new name).
CATEGORIES = (
    ("parent_contribution", "Contribuição de pais", "IN", "CONTRIBUTIONS"),
    ("donation", "Doações", "IN", "OTHER_INCOME"),
    ("other_income", "Outras entradas", "IN", "OTHER_INCOME"),
    ("apm_revenue", "Receitas da APM", "IN", "OTHER_INCOME"),
    ("teacher_reimbursement", "{teacher}", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("director_reimbursement", "Reembolso de diretor", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("school_supplies", "Compra de material", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("services", "Serviços", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("other_authorized", "Outras despesas autorizadas", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("bank_fees", "Tarifas bancárias", "OUT", "BANK_FEES"),
    ("refund", "Devolução", "IN", "REFUNDS"),
)


def _function(teacher_name: str) -> str:
    values = ", ".join(
        "(" + ", ".join(f"'{part.format(teacher=teacher_name)}'" for part in row) + ")"
        for row in CATEGORIES
    )
    return f"""
CREATE OR REPLACE FUNCTION public.schools_create_settings() RETURNS trigger {HEADER} AS $body$
BEGIN
    INSERT INTO public.school_settings (school_id, organization_id)
    VALUES (NEW.id, NEW.organization_id) ON CONFLICT DO NOTHING;
    INSERT INTO public.categories
        (organization_id, school_id, key, name, applies_to, report_group, requires_approval)
    SELECT NEW.organization_id, NEW.id, d.key, d.name, d.applies_to, d.report_group,
           d.key <> 'bank_fees'
    FROM (VALUES {values}) AS d (key, name, applies_to, report_group)
    ON CONFLICT DO NOTHING;
    RETURN NEW;
END
$body$
"""


def _rename(old: str, new: str) -> None:
    op.execute(
        f"UPDATE categories SET name = '{new}' "  # noqa: S608 (constants of this file)
        f"WHERE key = 'teacher_reimbursement' AND name = '{old}'"
    )


def _replace_function(teacher_name: str) -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(_function(teacher_name))
    op.execute("RESET ROLE")


def upgrade() -> None:
    _rename(OLD, NEW)
    _replace_function(NEW)


def downgrade() -> None:
    _rename(NEW, OLD)
    _replace_function(OLD)
