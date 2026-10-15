"""CSV and PDF statements: the column map of an account, where an import came from, review of PDF lines

Revision ID: 0019_statement_formats
Revises: 0018_bank_line_resolutions
Create Date: 2026-10-14

* `bank_accounts.csv_profile`: how the CSV of that bank is read (which column is the date, the text and
  the amount, the date format, the decimal mark), chosen once and kept. Small, and only data.
* `bank_statement_imports.source`: OFX, CSV or PDF.
* `bank_statement_lines.needs_review`: a line read from a PDF is a best-effort reading; the management
  must tick that it conferred the line before it becomes an entry of the ledger.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_statement_formats"
down_revision: str | None = "0018_bank_line_resolutions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE bank_accounts ADD COLUMN csv_profile jsonb")
    op.execute(
        "ALTER TABLE bank_accounts ADD CONSTRAINT ck_bank_accounts_csv_profile_shape "
        "CHECK (csv_profile IS NULL OR (jsonb_typeof(csv_profile) = 'object' "
        "AND length(csv_profile::text) <= 1000))"
    )
    op.execute("GRANT UPDATE (csv_profile) ON bank_accounts TO apm_app")
    op.execute("ALTER TABLE bank_statement_imports ADD COLUMN source text NOT NULL DEFAULT 'OFX'")
    op.execute(
        "ALTER TABLE bank_statement_imports ADD CONSTRAINT ck_bank_statement_imports_source_valid "
        "CHECK (source IN ('OFX', 'CSV', 'PDF'))"
    )
    op.execute("GRANT INSERT (source) ON bank_statement_imports TO apm_app")
    op.execute(
        "ALTER TABLE bank_statement_lines ADD COLUMN needs_review boolean NOT NULL DEFAULT false"
    )
    op.execute("GRANT INSERT (needs_review) ON bank_statement_lines TO apm_app")
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE bank_statement_lines DROP COLUMN IF EXISTS needs_review")
    op.execute("ALTER TABLE bank_statement_imports DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE bank_accounts DROP COLUMN IF EXISTS csv_profile")
    op.execute("RESET ROLE")
