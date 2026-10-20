"""the expenses paid with the PDDE money leave the cash of the APM

Revision ID: 0032_pdde_out_of_cash
Revises: 0031_expense_fund
Create Date: 2026-10-20

The cash statement of the APM (`statement_entries`, `statement_summary`, `statement_pending`) counted
every expense paid by the APM and every reimbursement. Since 0031 an expense says which money pays
it. One decided as PDDE is paid from the PDDE bank account, so neither it nor the reimbursement of
it moves the cash of the APM: the dashboard, the Livro Caixa, the closing and the balancete of the
APM show only the APM's money.

The three functions are the ones of 0007 with the same text, plus the PDDE filter (`CREATE OR REPLACE`,
same signature, so the grants stay). An expense with no fund (decided before 0031, or the bank
fees) counts as the APM's, as before; a month already closed does not change.
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0032_pdde_out_of_cash"
down_revision: str | None = "0031_expense_fund"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMES = ("statement_entries", "statement_summary", "statement_pending")

# The condition of an expense "of the APM's cash", and the one of a reimbursement whose expense is not the PDDE's.
_OLD_EXPENSE = "(f.kind <> 'EXPENSE' OR e.paid_by = 'APM')"
_NEW_EXPENSE = (
    "(f.kind <> 'EXPENSE' OR (e.paid_by = 'APM' AND e.fund IS DISTINCT FROM 'PDDE')) "
    "AND NOT (f.kind = 'REIMBURSEMENT' AND EXISTS (SELECT 1 FROM public.expenses px "
    "WHERE px.transaction_id = f.parent_transaction_id AND px.school_id = p_school "
    "AND px.fund = 'PDDE'))"
)
_OLD_PENDING_SUM = (
    "WHERE f.school_id = p_school AND f.kind = 'REIMBURSEMENT' AND f.status = 'PENDING'\n"
    "          AND f.occurred_at < w.t1"
)
_NEW_PENDING_SUM = (
    _OLD_PENDING_SUM + "\n          AND NOT EXISTS (SELECT 1 FROM public.expenses px "
    "WHERE px.transaction_id = f.parent_transaction_id AND px.school_id = p_school "
    "AND px.fund = 'PDDE')"
)
_OLD_PAYABLE = "OR (f.status = 'APPROVED' AND e.paid_by = 'APM')))"
_NEW_PAYABLE = (
    "OR (f.status = 'APPROVED' AND e.paid_by = 'APM' AND e.fund IS DISTINCT FROM 'PDDE')))"
)
_OLD_REIMBURSEMENT_ROW = "OR (f.kind = 'REIMBURSEMENT' AND f.status = 'PENDING')"
_NEW_REIMBURSEMENT_ROW = (
    "OR (f.kind = 'REIMBURSEMENT' AND f.status = 'PENDING' AND NOT EXISTS (SELECT 1 "
    "FROM public.expenses px WHERE px.transaction_id = f.parent_transaction_id "
    "AND px.school_id = p_school AND px.fund = 'PDDE'))"
)


def _original() -> dict[str, str]:
    """The text of the three functions as 0007 wrote them."""
    path = Path(__file__).with_name("0007_financial_schema.py")
    spec = importlib.util.spec_from_file_location("_apm_0007", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load revision 0007")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: str(module.FUNCTIONS[name]).strip() for name in _NAMES}


def _replace(text: str, old: str, new: str, count: int) -> str:
    if text.count(old) != count:
        raise RuntimeError(f"0007 changed: {old!r} found {text.count(old)} times, not {count}")
    return text.replace(old, new)


def _or_replace(text: str) -> str:
    return _replace(text, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def _filtered() -> dict[str, str]:
    original = _original()
    entries = _replace(original["statement_entries"], _OLD_EXPENSE, _NEW_EXPENSE, 2)
    summary = _replace(original["statement_summary"], _OLD_EXPENSE, _NEW_EXPENSE, 1)
    summary = _replace(summary, _OLD_PENDING_SUM, _NEW_PENDING_SUM, 1)
    pending = _replace(original["statement_pending"], _OLD_PAYABLE, _NEW_PAYABLE, 1)
    pending = _replace(pending, _OLD_REIMBURSEMENT_ROW, _NEW_REIMBURSEMENT_ROW, 1)
    return {
        "statement_entries": entries,
        "statement_summary": summary,
        "statement_pending": pending,
    }


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for text in _filtered().values():
        op.execute(_or_replace(text))
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for text in _original().values():
        op.execute(_or_replace(text))
    op.execute("RESET ROLE")
