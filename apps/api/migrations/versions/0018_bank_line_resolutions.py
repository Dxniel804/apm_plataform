"""what the management decided about a line of a bank statement

Revision ID: 0018_bank_line_resolutions
Revises: 0017_bank_reconciliation
Create Date: 2026-10-14

* `bank_line_resolutions`: one row per statement line the management resolved, written once.
  `REGISTERED`: the line became an entry of the ledger (a Pix straight to the key, a transfer or a
  bank fee), which the row points to. `IGNORED`: the line is not an entry of the APM, and WHY is
  required. A line can be resolved only once (so a double click, or two people at once, never
  books the money twice) and a ledger entry resolves only one line.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_bank_line_resolutions"
down_revision: str | None = "0017_bank_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
TABLE = "bank_line_resolutions"


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            line_id uuid NOT NULL,
            action text NOT NULL,
            reason text,
            transaction_id uuid,
            transaction_kind text,
            resolved_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_{TABLE} PRIMARY KEY (id),
            CONSTRAINT fk_{TABLE}_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_{TABLE}_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id) REFERENCES schools (id, organization_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_{TABLE}_line_id_bank_statement_lines
                FOREIGN KEY (line_id) REFERENCES bank_statement_lines (id) ON DELETE RESTRICT,
            CONSTRAINT fk_{TABLE}_transaction
                FOREIGN KEY (transaction_id, organization_id, school_id, transaction_kind)
                REFERENCES financial_transactions (id, organization_id, school_id, kind)
                ON DELETE RESTRICT,
            CONSTRAINT fk_{TABLE}_resolved_by_user_id_users
                FOREIGN KEY (resolved_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            -- A line is resolved once; an entry of the ledger resolves one line.
            CONSTRAINT uq_{TABLE}_school_id_line_id UNIQUE (school_id, line_id),
            CONSTRAINT uq_{TABLE}_school_id_transaction_id UNIQUE (school_id, transaction_id),
            CONSTRAINT ck_{TABLE}_action_valid CHECK (action IN ('IGNORED', 'REGISTERED')),
            CONSTRAINT ck_{TABLE}_shape CHECK (
                (action = 'IGNORED' AND transaction_id IS NULL AND transaction_kind IS NULL
                 AND length(btrim(coalesce(reason, ''))) BETWEEN 3 AND 200)
                OR (action = 'REGISTERED' AND reason IS NULL AND transaction_id IS NOT NULL
                    AND transaction_kind IN ('CONTRIBUTION', 'EXPENSE'))
            )
        )
        """
    )
    op.execute(f"CREATE INDEX ix_{TABLE}_school_id ON {TABLE} (school_id)")
    op.execute(
        f"CREATE TRIGGER {TABLE}_05_no_update BEFORE UPDATE ON public.{TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.forbid_update()"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_25_member BEFORE INSERT ON public.{TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.assert_active_member('resolved_by_user_id')"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_95_audit AFTER INSERT OR UPDATE ON public.{TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
        "'id,organization_id,school_id,line_id,action,transaction_id', 'reason', 'id', '')"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_no_delete BEFORE DELETE ON public.{TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.forbid_delete()"
    )
    op.execute(
        f"CREATE TRIGGER {TABLE}_no_truncate BEFORE TRUNCATE ON public.{TABLE} "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.forbid_truncate()"
    )
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {TABLE}_select ON {TABLE} FOR SELECT USING ({SCOPE})")
    op.execute(
        f"CREATE POLICY {TABLE}_insert ON {TABLE} FOR INSERT WITH CHECK ({SCOPE} AND EXISTS ("
        f"SELECT 1 FROM public.bank_statement_lines l WHERE l.id = {TABLE}.line_id "
        f"AND l.school_id = {TABLE}.school_id AND l.organization_id = {TABLE}.organization_id))"
    )
    op.execute(f"GRANT SELECT ON {TABLE} TO apm_app")
    op.execute(
        f"GRANT INSERT (organization_id, school_id, line_id, action, reason, transaction_id, "
        f"transaction_kind, resolved_by_user_id) ON {TABLE} TO apm_app"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
    op.execute("RESET ROLE")
