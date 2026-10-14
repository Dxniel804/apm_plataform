"""campaigns v2: the cost of a product, who gets what (student and class) and the delivery of an order

Revision ID: 0014_campaign_costs_deliveries
Revises: 0013_campaigns
Create Date: 2026-10-14

What the management needs to follow a campaign: how much came in, how much it cost, who bought and
what is left to deliver. Three additions, and the rules the DATABASE keeps whatever the application
does:

* `campaign_items.unit_cost_cents`: what one unit costs the APM (optional, 0 to R$ 10.000,00). A
  management metric: it is NOT a ledger entry. The real outflow is still the expense.
* `contribution_items.unit_cost_cents`: the COPY of that cost at the moment of the purchase, like the
  name and the price. The application never sends it: a trigger fills it from the product, so a cost
  changed later never touches an order already made, and a cost that came from the browser cannot get
  in. Insert-only like the rest of the row (`contribution_items_05_no_update`).
* `campaigns.ask_student_class` (default on): the family must say the student and the class, so the
  management knows to whom to deliver. The columns already exist in `contributions`; this flag only
  makes the application require them for the orders of that campaign.
* `campaign_deliveries`: the delivery state of an order (PENDING or DELIVERED), who marked it and
  when. Outside the ledger on purpose (the contributions stay as they are): a row appears when an
  order is first marked, and it can be switched back. The database refuses DELIVERED unless the
  order belongs to a campaign AND is PAID, and the audit trail records every change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_campaign_costs_deliveries"
down_revision: str | None = "0013_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
WRITE_CHECK = (
    f"({SCOPE} AND EXISTS (SELECT 1 FROM public.schools s "
    "WHERE s.id = campaign_deliveries.school_id "
    "AND s.organization_id = campaign_deliveries.organization_id))"
)

FUNCTIONS = {
    # Fills the copy of the cost from the product, whatever the caller sent.
    "contribution_items_copy_cost": f"""
CREATE FUNCTION public.contribution_items_copy_cost() RETURNS trigger {HEADER} AS $body$
BEGIN
    SELECT i.unit_cost_cents INTO NEW.unit_cost_cents
    FROM public.campaign_items i
    WHERE i.id = NEW.campaign_item_id AND i.campaign_id = NEW.campaign_id
      AND i.organization_id = NEW.organization_id AND i.school_id = NEW.school_id;
    RETURN NEW;
END
$body$
""",
    "campaign_deliveries_check": f"""
CREATE FUNCTION public.campaign_deliveries_check() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NEW.status = 'DELIVERED' AND NOT EXISTS (
        SELECT 1
        FROM public.contributions c
        JOIN public.financial_transactions f
          ON f.id = c.transaction_id AND f.school_id = c.school_id
        WHERE c.transaction_id = NEW.transaction_id AND c.organization_id = NEW.organization_id
          AND c.school_id = NEW.school_id AND c.campaign_id IS NOT NULL AND f.status = 'PAID'
    ) THEN
        RAISE EXCEPTION 'only a paid order of a campaign can be delivered'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
}


def _trigger(table: str, name: str, timing: str, function: str, *args: str) -> str:
    literal = ", ".join("'" + arg + "'" for arg in args)
    statement = "FOR EACH STATEMENT" if function == "forbid_truncate" else "FOR EACH ROW"
    return (
        f"CREATE TRIGGER {name} {timing} ON public.{table} {statement} "
        f"EXECUTE FUNCTION public.{function}({literal})"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")

    # --- cost, copy of the cost, student and class ------------------------------------------------
    op.execute("ALTER TABLE campaign_items ADD COLUMN unit_cost_cents bigint")
    op.execute(
        "ALTER TABLE campaign_items ADD CONSTRAINT ck_campaign_items_unit_cost_range "
        "CHECK (unit_cost_cents IS NULL OR unit_cost_cents BETWEEN 0 AND 1000000)"
    )
    op.execute("ALTER TABLE contribution_items ADD COLUMN unit_cost_cents bigint")
    op.execute(
        "ALTER TABLE contribution_items ADD CONSTRAINT ck_contribution_items_unit_cost_range "
        "CHECK (unit_cost_cents IS NULL OR unit_cost_cents BETWEEN 0 AND 1000000)"
    )
    op.execute("ALTER TABLE campaigns ADD COLUMN ask_student_class boolean NOT NULL DEFAULT true")
    # The application writes the cost of a product and the flag of a campaign. It never writes the
    # copy: the trigger does.
    op.execute(
        "GRANT INSERT (unit_cost_cents), UPDATE (unit_cost_cents) ON campaign_items TO apm_app"
    )
    op.execute(
        "GRANT INSERT (ask_student_class), UPDATE (ask_student_class) ON campaigns TO apm_app"
    )

    for function in FUNCTIONS.values():
        op.execute(function)
    op.execute(
        "REVOKE ALL ON FUNCTION public.contribution_items_copy_cost(), "
        "public.campaign_deliveries_check() FROM PUBLIC"
    )
    # "15": before the check of the copy of name and price (20), and the audit (95).
    op.execute(
        "CREATE TRIGGER contribution_items_15_copy_cost BEFORE INSERT ON public.contribution_items "
        "FOR EACH ROW EXECUTE FUNCTION public.contribution_items_copy_cost()"
    )

    # The audit trail knows the new columns (numbers and flags only, never free text).
    op.execute("DROP TRIGGER campaigns_95_audit ON public.campaigns")
    op.execute(
        _trigger(
            "campaigns", "campaigns_95_audit", "AFTER INSERT OR UPDATE", "audit_row_change",
            "id,organization_id,school_id,created_by_user_id,status,starts_on,ends_on,ended_at,"
            "cover_content_type,cover_size_bytes,cover_sha256,cover_version,ask_student_class",
            "title,description,cover_storage_key", "id", "",
        )
    )  # fmt: skip
    op.execute("DROP TRIGGER campaign_items_95_audit ON public.campaign_items")
    op.execute(
        _trigger(
            "campaign_items", "campaign_items_95_audit", "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,campaign_id,price_cents,max_per_order,position,"
            "is_active,image_content_type,image_size_bytes,image_sha256,image_version,"
            "unit_cost_cents",
            "name,description,image_storage_key", "id", "",
        )
    )  # fmt: skip
    op.execute("DROP TRIGGER contribution_items_95_audit ON public.contribution_items")
    op.execute(
        _trigger(
            "contribution_items", "contribution_items_95_audit", "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,transaction_id,campaign_id,campaign_item_id,"
            "unit_price_cents,quantity,unit_cost_cents",
            "item_name", "id", "",
        )
    )  # fmt: skip

    # --- the delivery of an order -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE campaign_deliveries (
            transaction_id uuid NOT NULL,
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'DELIVERED',
            changed_by_user_id uuid NOT NULL,
            changed_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_campaign_deliveries
                PRIMARY KEY (transaction_id, organization_id, school_id),
            CONSTRAINT fk_campaign_deliveries_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_campaign_deliveries_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_campaign_deliveries_transaction_id_contributions
                FOREIGN KEY (transaction_id, organization_id, school_id)
                REFERENCES contributions (transaction_id, organization_id, school_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_campaign_deliveries_changed_by_user_id_users
                FOREIGN KEY (changed_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_campaign_deliveries_status_valid
                CHECK (status IN ('PENDING', 'DELIVERED'))
        )
        """
    )
    op.execute("CREATE INDEX ix_campaign_deliveries_school_id ON campaign_deliveries (school_id)")
    for statement in (
        _trigger(
            "campaign_deliveries", "campaign_deliveries_05_immutable", "BEFORE UPDATE",
            "assert_immutable_columns",
            "transaction_id", "organization_id", "school_id", "created_at",
        ),
        "CREATE TRIGGER campaign_deliveries_20_check BEFORE INSERT OR UPDATE "
        "ON public.campaign_deliveries FOR EACH ROW "
        "EXECUTE FUNCTION public.campaign_deliveries_check()",
        _trigger(
            "campaign_deliveries", "campaign_deliveries_25_member",
            "BEFORE INSERT OR UPDATE", "assert_active_member", "changed_by_user_id",
        ),
        _trigger(
            "campaign_deliveries", "campaign_deliveries_95_audit", "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "transaction_id,organization_id,school_id,status,changed_by_user_id", "",
            "transaction_id", "tx",
        ),
        _trigger("campaign_deliveries", "campaign_deliveries_no_delete", "BEFORE DELETE",
                 "forbid_delete"),
        _trigger("campaign_deliveries", "campaign_deliveries_no_truncate", "BEFORE TRUNCATE",
                 "forbid_truncate"),
    ):  # fmt: skip
        op.execute(statement)

    op.execute("ALTER TABLE campaign_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE campaign_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY campaign_deliveries_select ON campaign_deliveries FOR SELECT USING ({SCOPE})"
    )
    op.execute(
        "CREATE POLICY campaign_deliveries_insert ON campaign_deliveries FOR INSERT "
        f"WITH CHECK ({WRITE_CHECK})"
    )
    op.execute(
        "CREATE POLICY campaign_deliveries_update ON campaign_deliveries FOR UPDATE "
        f"USING ({SCOPE}) WITH CHECK ({WRITE_CHECK})"
    )
    op.execute("GRANT SELECT ON campaign_deliveries TO apm_app")
    op.execute(
        "GRANT INSERT (transaction_id, organization_id, school_id, status, changed_by_user_id) "
        "ON campaign_deliveries TO apm_app"
    )
    op.execute(
        "GRANT UPDATE (status, changed_by_user_id, changed_at) ON campaign_deliveries TO apm_app"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TABLE IF EXISTS campaign_deliveries")
    op.execute(
        "DROP TRIGGER IF EXISTS contribution_items_15_copy_cost ON public.contribution_items"
    )
    op.execute("DROP TRIGGER campaigns_95_audit ON public.campaigns")
    op.execute("DROP TRIGGER campaign_items_95_audit ON public.campaign_items")
    op.execute("DROP TRIGGER contribution_items_95_audit ON public.contribution_items")
    op.execute(
        "ALTER TABLE contribution_items DROP CONSTRAINT ck_contribution_items_unit_cost_range"
    )
    op.execute("ALTER TABLE contribution_items DROP COLUMN unit_cost_cents")
    op.execute("ALTER TABLE campaign_items DROP CONSTRAINT ck_campaign_items_unit_cost_range")
    op.execute("ALTER TABLE campaign_items DROP COLUMN unit_cost_cents")
    op.execute("ALTER TABLE campaigns DROP COLUMN ask_student_class")
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{name}()")
    # The audit triggers of 0013, back as they were.
    op.execute(
        _trigger(
            "campaigns", "campaigns_95_audit", "AFTER INSERT OR UPDATE", "audit_row_change",
            "id,organization_id,school_id,created_by_user_id,status,starts_on,ends_on,ended_at,"
            "cover_content_type,cover_size_bytes,cover_sha256,cover_version",
            "title,description,cover_storage_key", "id", "",
        )
    )  # fmt: skip
    op.execute(
        _trigger(
            "campaign_items", "campaign_items_95_audit", "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,campaign_id,price_cents,max_per_order,position,"
            "is_active,image_content_type,image_size_bytes,image_sha256,image_version",
            "name,description,image_storage_key", "id", "",
        )
    )  # fmt: skip
    op.execute(
        _trigger(
            "contribution_items", "contribution_items_95_audit", "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,transaction_id,campaign_id,campaign_item_id,"
            "unit_price_cents,quantity",
            "item_name", "id", "",
        )
    )  # fmt: skip
    op.execute("RESET ROLE")
