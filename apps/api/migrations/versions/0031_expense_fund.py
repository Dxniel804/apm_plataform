"""which money pays an expense: the APM or the PDDE

Revision ID: 0031_expense_fund
Revises: 0030_pdde_forms
Create Date: 2026-10-20

* `expenses.fund` is `APM` or `PDDE`. It is written once, together with the decision of whoever
  approves the expense (the site shows the secretaria the choice the category suggests, and she can
  change it). It stays NULL while the expense is not decided, and for a rejected one; the bank fees,
  born approved, have none, and a reader treats NULL as `APM`.
* The expenses decided before this revision are the APM's: they were paid from the APM account.
* The audit trail copies the new column (it is not free text).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_expense_fund"
down_revision: str | None = "0030_pdde_forms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SET_ONCE_BEFORE = "'approved_by_user_id', 'approved_at', 'approved_amount_cents', 'decision_reason'"
SET_ONCE_AFTER = SET_ONCE_BEFORE + ", 'fund'"
AUDIT_BEFORE = (
    "transaction_id,paid_by,payment_method,submitted_by_user_id,approved_by_user_id,"
    "approved_at,approved_amount_cents"
)
AUDIT_AFTER = AUDIT_BEFORE + ",fund"
AUDIT_FLAGGED = "description,vendor,purchase_reason,decision_reason,correction_reason"


def _set_once(columns: str) -> str:
    return (
        "CREATE TRIGGER expenses_10_set_once BEFORE UPDATE ON public.expenses "
        f"FOR EACH ROW EXECUTE FUNCTION public.assert_set_once_columns({columns})"
    )


def _audit(copied: str) -> str:
    return (
        "CREATE TRIGGER expenses_95_audit AFTER INSERT OR UPDATE ON public.expenses "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
        f"'{copied}', '{AUDIT_FLAGGED}', 'transaction_id', 'tx')"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE expenses ADD COLUMN fund text")
    op.execute(
        "ALTER TABLE expenses ADD CONSTRAINT ck_expenses_fund_valid "
        "CHECK (fund IS NULL OR fund IN ('APM', 'PDDE'))"
    )
    op.execute("GRANT SELECT (fund), UPDATE (fund) ON expenses TO apm_app")
    # Before the guard changes: what was decided before this revision is the APM's.
    op.execute("UPDATE expenses SET fund = 'APM' WHERE approved_by_user_id IS NOT NULL")
    op.execute("DROP TRIGGER expenses_10_set_once ON public.expenses")
    op.execute(_set_once(SET_ONCE_AFTER))
    op.execute("DROP TRIGGER expenses_95_audit ON public.expenses")
    op.execute(_audit(AUDIT_AFTER))
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TRIGGER expenses_95_audit ON public.expenses")
    op.execute(_audit(AUDIT_BEFORE))
    op.execute("DROP TRIGGER expenses_10_set_once ON public.expenses")
    op.execute(_set_once(SET_ONCE_BEFORE))
    op.execute("ALTER TABLE expenses DROP CONSTRAINT ck_expenses_fund_valid")
    op.execute("ALTER TABLE expenses DROP COLUMN fund")
    op.execute("RESET ROLE")
