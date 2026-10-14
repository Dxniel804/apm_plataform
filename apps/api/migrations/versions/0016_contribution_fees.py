"""the fee of the payment gateway of a contribution: gross, fee and net

Revision ID: 0016_contribution_fees
Revises: 0015_school_link_settings
Create Date: 2026-10-14

Every gateway charges a fee per payment and sends the rest to the school (decision of the owner: no
split and no cut for the platform). The ledger keeps the GROSS amount of a contribution (what the
family paid); this table keeps, next to it, what the gateway kept, so the school can see both and
the bank statement can be reconciled (M5, M6).

* `contribution_fees`: one row per paid contribution, written by the webhook at the moment the
  payment is confirmed and never changed. `gross_cents` must be the amount of the ledger row, the
  fee never exceeds it, and the net is computed by the database from who pays the fee: the SCHOOL
  (it receives gross minus fee) or the PAYER (the family paid the fee on top; the school receives
  the gross). Only SCHOOL is used until the owner decides who pays.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_contribution_fees"
down_revision: str | None = "0015_school_link_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
WRITE_CHECK = (
    f"({SCOPE} AND EXISTS (SELECT 1 FROM public.schools s "
    "WHERE s.id = contribution_fees.school_id "
    "AND s.organization_id = contribution_fees.organization_id))"
)

CHECK_FUNCTION = f"""
CREATE FUNCTION public.contribution_fees_check() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.financial_transactions f
        WHERE f.id = NEW.transaction_id AND f.organization_id = NEW.organization_id
          AND f.school_id = NEW.school_id AND f.kind = 'CONTRIBUTION'
          AND f.status = 'PAID' AND f.amount_cents = NEW.gross_cents
    ) THEN
        RAISE EXCEPTION 'the fee is recorded for a PAID contribution, over its own amount'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
"""


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(
        """
        CREATE TABLE contribution_fees (
            transaction_id uuid NOT NULL,
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            gross_cents bigint NOT NULL,
            gateway_fee_cents bigint NOT NULL,
            fee_payer text NOT NULL DEFAULT 'SCHOOL',
            net_cents bigint GENERATED ALWAYS AS (
                CASE fee_payer WHEN 'SCHOOL' THEN gross_cents - gateway_fee_cents ELSE gross_cents END
            ) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_contribution_fees
                PRIMARY KEY (transaction_id, organization_id, school_id),
            CONSTRAINT fk_contribution_fees_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_contribution_fees_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_contribution_fees_transaction_id_contributions
                FOREIGN KEY (transaction_id, organization_id, school_id)
                REFERENCES contributions (transaction_id, organization_id, school_id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_contribution_fees_gross_positive CHECK (gross_cents > 0),
            CONSTRAINT ck_contribution_fees_fee_range
                CHECK (gateway_fee_cents >= 0 AND gateway_fee_cents <= gross_cents),
            CONSTRAINT ck_contribution_fees_fee_payer_valid
                CHECK (fee_payer IN ('SCHOOL', 'PAYER'))
        )
        """
    )
    op.execute("CREATE INDEX ix_contribution_fees_school_id ON contribution_fees (school_id)")
    op.execute(CHECK_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION public.contribution_fees_check() FROM PUBLIC")
    for statement in (
        "CREATE TRIGGER contribution_fees_05_no_update BEFORE UPDATE ON public.contribution_fees "
        "FOR EACH ROW EXECUTE FUNCTION public.forbid_update()",
        "CREATE TRIGGER contribution_fees_20_check BEFORE INSERT ON public.contribution_fees "
        "FOR EACH ROW EXECUTE FUNCTION public.contribution_fees_check()",
        "CREATE TRIGGER contribution_fees_95_audit AFTER INSERT OR UPDATE ON public.contribution_fees "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
        "'transaction_id,gross_cents,gateway_fee_cents,fee_payer,net_cents', '', "
        "'transaction_id', 'tx')",
        "CREATE TRIGGER contribution_fees_no_delete BEFORE DELETE ON public.contribution_fees "
        "FOR EACH ROW EXECUTE FUNCTION public.forbid_delete()",
        "CREATE TRIGGER contribution_fees_no_truncate BEFORE TRUNCATE ON public.contribution_fees "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.forbid_truncate()",
    ):
        op.execute(statement)
    op.execute("ALTER TABLE contribution_fees ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE contribution_fees FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY contribution_fees_select ON contribution_fees FOR SELECT USING ({SCOPE})"
    )
    op.execute(
        f"CREATE POLICY contribution_fees_insert ON contribution_fees FOR INSERT WITH CHECK ({WRITE_CHECK})"
    )
    op.execute("GRANT SELECT ON contribution_fees TO apm_app")
    op.execute(
        "GRANT INSERT (transaction_id, organization_id, school_id, gross_cents, gateway_fee_cents, "
        "fee_payer) ON contribution_fees TO apm_app"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TABLE IF EXISTS contribution_fees")
    op.execute("DROP FUNCTION IF EXISTS public.contribution_fees_check()")
    op.execute("RESET ROLE")
