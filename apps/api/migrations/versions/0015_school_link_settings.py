"""the reference month of a contribution and the goals and texts of the school settings

Revision ID: 0015_school_link_settings
Revises: 0014_campaign_costs_deliveries
Create Date: 2026-10-14

* `contributions.reference_month`: the month a contribution is FOR (the first day of it), chosen by the
  family in the public flow. Optional (a campaign order, a cash entry or an older contribution has
  none), written once with the row and never changed, and always a first day of a month.
* `school_settings.monthly_goal_cents` and `expected_contributions`: what the school hopes to collect
  in a month and how many contributions it expects. They feed the "goal and adhesion" card of the
  dashboard (M3); nothing here decides money.
* `school_settings.free_amount_text`: a sentence the family reads next to the free amount field.

The cash statement function `statement_entries` is NOT touched (the hash of the monthly closing
depends on it): the reference month reaches the statement through its own query.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_school_link_settings"
down_revision: str | None = "0014_campaign_costs_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The columns of a contribution that never change: those of 0013, plus the reference month.
IMMUTABLE_BEFORE = (
    "transaction_id",
    "organization_id",
    "school_id",
    "kind",
    "method",
    "external_reference",
    "receipt_token_hash",
    "receipt_expires_at",
    "idempotency_key",
    "campaign_id",
    "created_at",
)
IMMUTABLE_AFTER = (*IMMUTABLE_BEFORE[:-1], "reference_month", "created_at")

SETTINGS_AUDIT_BEFORE = (
    "school_id,timezone,min_contribution_cents,max_contribution_cents,suggested_amounts_cents,"
    "allow_custom_amount,pix_expiration_minutes,required_fields,optional_fields,brand_accent,"
    "brand_accent_contrast,approval_limit_cents"
)
SETTINGS_AUDIT_AFTER = SETTINGS_AUDIT_BEFORE + ",monthly_goal_cents,expected_contributions"
CONTRIBUTIONS_AUDIT_BEFORE = "transaction_id,method,receipt_expires_at"
CONTRIBUTIONS_AUDIT_AFTER = CONTRIBUTIONS_AUDIT_BEFORE + ",reference_month"
CONTRIBUTIONS_FLAGGED = (
    "guardian_name,student_name,class_name,contributor_email,contributor_phone,"
    "receipt_token_hash,review_decision_reason,external_reference"
)


def _literal(values: Sequence[str]) -> str:
    return ", ".join("'" + value + "'" for value in values)


def _immutable(columns: Sequence[str]) -> str:
    return (
        "CREATE TRIGGER contributions_05_immutable BEFORE UPDATE ON public.contributions "
        f"FOR EACH ROW EXECUTE FUNCTION public.assert_immutable_columns({_literal(columns)})"
    )


def _audit(table: str, copied: str, flagged: str, key: str, reference: str) -> str:
    return (
        f"CREATE TRIGGER {table}_95_audit AFTER INSERT OR UPDATE ON public.{table} "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
        f"'{copied}', '{flagged}', '{key}', '{reference}')"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")

    op.execute("ALTER TABLE contributions ADD COLUMN reference_month date")
    op.execute(
        "ALTER TABLE contributions ADD CONSTRAINT ck_contributions_reference_month_first_day "
        "CHECK (reference_month IS NULL OR reference_month = date_trunc('month', reference_month)::date)"
    )
    op.execute(
        "GRANT SELECT (reference_month), INSERT (reference_month) ON contributions TO apm_app"
    )
    op.execute("DROP TRIGGER contributions_05_immutable ON public.contributions")
    op.execute(_immutable(IMMUTABLE_AFTER))
    op.execute("DROP TRIGGER contributions_95_audit ON public.contributions")
    op.execute(
        _audit(
            "contributions",
            CONTRIBUTIONS_AUDIT_AFTER,
            CONTRIBUTIONS_FLAGGED,
            "transaction_id",
            "tx",
        )
    )

    op.execute("ALTER TABLE school_settings ADD COLUMN monthly_goal_cents bigint")
    op.execute("ALTER TABLE school_settings ADD COLUMN expected_contributions integer")
    op.execute("ALTER TABLE school_settings ADD COLUMN free_amount_text text")
    op.execute(
        "ALTER TABLE school_settings ADD CONSTRAINT ck_school_settings_monthly_goal_range "
        "CHECK (monthly_goal_cents IS NULL OR monthly_goal_cents BETWEEN 100 AND 100000000000)"
    )
    op.execute(
        "ALTER TABLE school_settings ADD CONSTRAINT ck_school_settings_expected_contributions_range "
        "CHECK (expected_contributions IS NULL OR expected_contributions BETWEEN 1 AND 100000)"
    )
    op.execute(
        "ALTER TABLE school_settings ADD CONSTRAINT ck_school_settings_free_amount_text_length "
        "CHECK (free_amount_text IS NULL OR length(btrim(free_amount_text)) BETWEEN 1 AND 300)"
    )
    op.execute(
        "GRANT SELECT (monthly_goal_cents, expected_contributions, free_amount_text), "
        "UPDATE (monthly_goal_cents, expected_contributions, free_amount_text) "
        "ON school_settings TO apm_app"
    )
    op.execute("DROP TRIGGER school_settings_95_audit ON public.school_settings")
    op.execute(_audit("school_settings", SETTINGS_AUDIT_AFTER, "free_amount_text", "school_id", ""))
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TRIGGER school_settings_95_audit ON public.school_settings")
    op.execute(
        "ALTER TABLE school_settings DROP CONSTRAINT ck_school_settings_free_amount_text_length"
    )
    op.execute(
        "ALTER TABLE school_settings DROP CONSTRAINT ck_school_settings_expected_contributions_range"
    )
    op.execute("ALTER TABLE school_settings DROP CONSTRAINT ck_school_settings_monthly_goal_range")
    op.execute("ALTER TABLE school_settings DROP COLUMN free_amount_text")
    op.execute("ALTER TABLE school_settings DROP COLUMN expected_contributions")
    op.execute("ALTER TABLE school_settings DROP COLUMN monthly_goal_cents")
    op.execute(_audit("school_settings", SETTINGS_AUDIT_BEFORE, "", "school_id", ""))

    op.execute("DROP TRIGGER contributions_95_audit ON public.contributions")
    op.execute("DROP TRIGGER contributions_05_immutable ON public.contributions")
    op.execute(
        "ALTER TABLE contributions DROP CONSTRAINT ck_contributions_reference_month_first_day"
    )
    op.execute("ALTER TABLE contributions DROP COLUMN reference_month")
    op.execute(_immutable(IMMUTABLE_BEFORE))
    op.execute(
        _audit(
            "contributions",
            CONTRIBUTIONS_AUDIT_BEFORE,
            CONTRIBUTIONS_FLAGGED,
            "transaction_id",
            "tx",
        )
    )
    op.execute("RESET ROLE")
