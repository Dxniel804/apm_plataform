"""balancete: the purposes of the accountant's monthly sheet and the balances she lists by place

Revision ID: 0027_balancete
Revises: 0026_central_link_check
Create Date: 2026-10-19

The accountant of an APM hands the school a monthly balancete: the balance carried from the month
before (in cash, in the bank, invested), the revenue, the permanent goods bought, the expenses by
purpose, and where the money is at the end. This revision gives the product what it needs to draw the
same sheet, without touching the ledger or its functions:

* Nine default purposes (expenses) with the names the accountant uses: stationery, office, teaching
  material, cleaning, animals, maintenance of equipment, maintenance material and, as permanent goods,
  furniture and machines (the keys that start with `capital_` are the "bens permanentes" of the
  sheet). They go in the report group of the other expenses, so every database function of the
  ledger (the statement, the summary, the closing and its hash) reads them like any other expense.
* `balancete_balances`: what the ledger does not know, typed by the treasurer.
  - `OPENING` (one is enough): what the school already had the day it started to use the system,
    by place (bank, cash, invested). The ledger starts at zero, so without this the balances of a
    school that did not start from nothing would never match the bank.
  - `MONTH`: at the end of a month, how much is in cash and how much is invested. The bank is what is
    left of the total; it is never typed twice.
  Insert-only: a correction is a new row and the latest one counts, so nothing is lost and the audit
  trail shows who changed what.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_balancete"
down_revision: str | None = "0026_central_link_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)

# The default purposes of a school: the list of 0013 plus the nine of the accountant.
CATEGORIES = (
    ("parent_contribution", "Contribuição de pais", "IN", "CONTRIBUTIONS"),
    ("donation", "Doações", "IN", "OTHER_INCOME"),
    ("other_income", "Outras entradas", "IN", "OTHER_INCOME"),
    ("apm_revenue", "Receitas da APM", "IN", "OTHER_INCOME"),
    ("teacher_reimbursement", "Reembolso de funcionário", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("director_reimbursement", "Reembolso de diretor", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("school_supplies", "Compra de material", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("services", "Serviços", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("other_authorized", "Outras despesas autorizadas", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("bank_fees", "Tarifas bancárias", "OUT", "BANK_FEES"),
    ("refund", "Devolução", "IN", "REFUNDS"),
    ("campaign_sales", "Vendas de campanha", "IN", "OTHER_INCOME"),
)
ACCOUNTANT = (
    ("stationery", "Impressos e material de expediente", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("office", "Despesas de escritório", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("teaching_material", "Material didático e pedagógico", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("cleaning_supplies", "Material de limpeza e higiene", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("animals", "Despesas com animais", "OUT", "EXPENSES_REIMBURSEMENTS"),
    (
        "equipment_maintenance",
        "Manutenção de máquinas, equipamentos e móveis",
        "OUT",
        "EXPENSES_REIMBURSEMENTS",
    ),
    (
        "maintenance_material",
        "Material de manutenção e conservação",
        "OUT",
        "EXPENSES_REIMBURSEMENTS",
    ),
    ("capital_furniture", "Compra de móveis", "OUT", "EXPENSES_REIMBURSEMENTS"),
    ("capital_equipment", "Compra de máquinas e equipamentos", "OUT", "EXPENSES_REIMBURSEMENTS"),
)


def _write_check(table: str) -> str:
    return (
        f"({SCOPE} AND EXISTS (SELECT 1 FROM public.schools s "
        f"WHERE s.id = {table}.school_id AND s.organization_id = {table}.organization_id))"
    )


def _category_function(rows: tuple[tuple[str, str, str, str], ...]) -> str:
    values = ", ".join("(" + ", ".join(f"'{part}'" for part in row) + ")" for row in rows)
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


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(_category_function((*CATEGORIES, *ACCOUNTANT)))
    op.execute(
        """
        CREATE TABLE balancete_balances (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            kind text NOT NULL,
            period_start date,
            bank_cents bigint,
            cash_cents bigint NOT NULL,
            investment_cents bigint NOT NULL,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_balancete_balances PRIMARY KEY (id),
            CONSTRAINT fk_balancete_balances_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_balancete_balances_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id) REFERENCES schools (id, organization_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_balancete_balances_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_balancete_balances_kind_valid CHECK (kind IN ('OPENING', 'MONTH')),
            -- OPENING has no month and gives the bank too; MONTH is a first day and gives no bank.
            CONSTRAINT ck_balancete_balances_shape CHECK (
                (kind = 'OPENING' AND period_start IS NULL AND bank_cents IS NOT NULL)
                OR (kind = 'MONTH' AND period_start IS NOT NULL AND bank_cents IS NULL
                    AND extract(day FROM period_start) = 1)
            ),
            CONSTRAINT ck_balancete_balances_amounts CHECK (
                cash_cents BETWEEN 0 AND 100000000000
                AND investment_cents BETWEEN 0 AND 100000000000
                AND (bank_cents IS NULL OR bank_cents BETWEEN -100000000000 AND 100000000000)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_balancete_balances_school_kind_period "
        "ON balancete_balances (school_id, kind, period_start, created_at DESC)"
    )

    def trig(name: str, timing: str, fn: str, *args: str, each: str = "ROW") -> None:
        literal = ", ".join("'" + a + "'" for a in args)
        op.execute(
            f"CREATE TRIGGER {name} {timing} ON public.balancete_balances "
            f"FOR EACH {each} EXECUTE FUNCTION public.{fn}({literal})"
        )

    trig("balancete_balances_05_no_update", "BEFORE UPDATE", "forbid_update")
    trig(
        "balancete_balances_25_member",
        "BEFORE INSERT",
        "assert_active_member",
        "created_by_user_id",
    )
    trig(
        "balancete_balances_95_audit",
        "AFTER INSERT OR UPDATE",
        "audit_row_change",
        "id,organization_id,school_id,kind,period_start,bank_cents,cash_cents,investment_cents",
        "",
        "id",
        "",
    )
    trig("balancete_balances_no_delete", "BEFORE DELETE", "forbid_delete")
    trig("balancete_balances_no_truncate", "BEFORE TRUNCATE", "forbid_truncate", each="STATEMENT")
    op.execute("ALTER TABLE balancete_balances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE balancete_balances FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY balancete_balances_select ON balancete_balances FOR SELECT USING ({SCOPE})"
    )
    op.execute(
        "CREATE POLICY balancete_balances_insert ON balancete_balances FOR INSERT "
        f"WITH CHECK ({_write_check('balancete_balances')})"
    )
    op.execute("GRANT SELECT ON balancete_balances TO apm_app")
    op.execute(
        "GRANT INSERT (organization_id, school_id, kind, period_start, bank_cents, cash_cents, "
        "investment_cents, created_by_user_id) ON balancete_balances TO apm_app"
    )
    op.execute("RESET ROLE")
    # The schools that exist get the nine purposes now. Like the backfills of 0007, 0011 and 0013 this
    # runs as the admin: with an admin that row level security hides the categories from, nothing is
    # inserted and the school only lacks the new names until somebody adds them.
    values = ", ".join("(" + ", ".join(f"'{part}'" for part in row) + ")" for row in ACCOUNTANT)
    op.execute(
        "INSERT INTO categories (organization_id, school_id, key, name, applies_to, report_group, "
        "requires_approval) "
        "SELECT s.organization_id, s.id, d.key, d.name, d.applies_to, d.report_group, true "
        f"FROM schools s CROSS JOIN (VALUES {values}) AS d (key, name, applies_to, report_group) "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    # The table goes. The nine purposes stay: a ledger row may already be filed under one, and an
    # unused default is harmless (the same choice as 0011 and 0013).
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TABLE IF EXISTS balancete_balances")
    op.execute(_category_function(CATEGORIES))
    op.execute("RESET ROLE")
