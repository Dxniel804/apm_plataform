"""campaigns: the management sells products to the families (a party, a kit), with a cart

Revision ID: 0013_campaigns
Revises: 0012_staff_requests
Create Date: 2026-10-13

A campaign has a title, a text, a cover and products (name, text, image, price, a limit per order).
The management writes them; the family picks quantities on the public page and pays by Pix. What
this revision adds, and the rules the DATABASE keeps whatever the application does:

* `campaigns` and `campaign_items`: tenant tables like the others (docs/tenancy.md, "How to create
  a new tenant table"): organization and school on both, composite foreign keys, every unique
  index carrying `school_id`, writes by column, no DELETE for the application role (a product that
  was sold is switched off, never removed), the final state ENDED frozen, an audit trail that never
  copies free text.
* `contribution_items`: the COPY of what an order bought (name, unit price, quantity), insert-only.
  A price changed later never touches an order already made. Three rules at the database:
  - before it is written, the product must be sold NOW (campaign ACTIVE and inside its dates,
    product active, quantity within its limit) and the copy must be the CURRENT name and price: a
    price that came from the browser cannot get in, whatever the code above does;
  - at COMMIT, the amount of a contribution of a campaign is exactly the sum of its items, it has
    at least one, and they all belong to the campaign of the contribution (the total is never
    decided by the page);
  - the copy never changes and is never removed.
* `contributions.campaign_id` (written once with the row, never changed) ties the contribution to
  its campaign; a contribution without a campaign has no items.
* A default category "Vendas de campanha" (`campaign_sales`, an entry of the report group
  OTHER_INCOME): the revenue of a campaign shows as its own line of the closing report, apart from
  the contributions of the parents.

The images (a cover and one per product) are PUBLIC once the campaign is on: only their key, type,
size and sha256 are in the database; the bytes live in the attachment store, with the metadata of
the photo removed (app/storage/image_clean.py).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_campaigns"
down_revision: str | None = "0012_staff_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEX64 = "^[0-9a-f]{64}$"
HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
TABLES = ("campaigns", "campaign_items", "contribution_items")
STATUSES = "'DRAFT', 'ACTIVE', 'ENDED'"
IMAGE_TYPES = "'image/png', 'image/jpeg', 'image/webp'"

# The same scope predicate of the other tenant tables (0004, 0007, 0012).
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)

# The default purposes of a school: the list of 0011 plus the campaigns.
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
)
CAMPAIGN_CATEGORY = ("campaign_sales", "Vendas de campanha", "IN", "OTHER_INCOME")

# The columns of contributions that never change: those of 0008, plus the campaign.
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
    "created_at",
)
IMMUTABLE_AFTER = (*IMMUTABLE_BEFORE[:-1], "campaign_id", "created_at")


def _write_check(table: str) -> str:
    in_school = (
        "EXISTS (SELECT 1 FROM public.schools s "
        f"WHERE s.id = {table}.school_id AND s.organization_id = {table}.organization_id)"
    )
    return f"({SCOPE} AND {in_school})"


# "Is this campaign on sale today?": ACTIVE, and today (in the time zone of the school) inside its
# dates. One predicate for the trigger below; the application reads the same thing in SQL.
OPEN_NOW = """
    c.status = 'ACTIVE'
    AND (c.starts_on IS NULL
         OR c.starts_on <= (now() AT TIME ZONE coalesce(
                (SELECT ss.timezone FROM public.school_settings ss WHERE ss.school_id = c.school_id),
                'America/Sao_Paulo'))::date)
    AND (c.ends_on IS NULL
         OR c.ends_on >= (now() AT TIME ZONE coalesce(
                (SELECT ss.timezone FROM public.school_settings ss WHERE ss.school_id = c.school_id),
                'America/Sao_Paulo'))::date)
"""

FUNCTIONS = {
    "campaigns_check_change": f"""
CREATE FUNCTION public.campaigns_check_change() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NOT (
            (OLD.status = 'DRAFT' AND NEW.status IN ('ACTIVE', 'ENDED'))
            OR (OLD.status = 'ACTIVE' AND NEW.status = 'ENDED')
        ) THEN
            RAISE EXCEPTION 'a campaign cannot go from % to %', OLD.status, NEW.status
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF NEW.status = 'ACTIVE' AND NOT EXISTS (
            SELECT 1 FROM public.campaign_items i
            WHERE i.campaign_id = NEW.id AND i.organization_id = NEW.organization_id
              AND i.school_id = NEW.school_id AND i.is_active
        ) THEN
            RAISE EXCEPTION 'a campaign needs an active product to go on sale'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END
$body$
""",
    "campaign_items_check_state": f"""
CREATE FUNCTION public.campaign_items_check_state() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.campaigns c
        WHERE c.id = NEW.campaign_id AND c.organization_id = NEW.organization_id
          AND c.school_id = NEW.school_id AND c.status <> 'ENDED'
    ) THEN
        RAISE EXCEPTION 'the products of an ended campaign do not change'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
    "contribution_items_check_item": f"""
CREATE FUNCTION public.contribution_items_check_item() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.campaign_items i
        JOIN public.campaigns c ON c.id = i.campaign_id AND c.school_id = i.school_id
        WHERE i.id = NEW.campaign_item_id AND i.campaign_id = NEW.campaign_id
          AND i.organization_id = NEW.organization_id AND i.school_id = NEW.school_id
          AND i.is_active
          AND i.name = NEW.item_name
          AND i.price_cents = NEW.unit_price_cents
          AND (i.max_per_order IS NULL OR NEW.quantity <= i.max_per_order)
          AND ({OPEN_NOW})
    ) THEN
        RAISE EXCEPTION 'the product is not on sale as written (campaign, dates, name, price or quantity)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
    # At COMMIT, so the order of the statements does not matter and the final rows are read.
    "contribution_items_check_total": f"""
CREATE FUNCTION public.contribution_items_check_total() RETURNS trigger {HEADER} AS $body$
DECLARE
    v_campaign uuid;
    v_amount bigint;
    v_sum bigint;
    v_lines integer;
    v_foreign integer;
BEGIN
    SELECT c.campaign_id, f.amount_cents INTO v_campaign, v_amount
    FROM public.contributions c
    JOIN public.financial_transactions f ON f.id = c.transaction_id AND f.school_id = c.school_id
    WHERE c.transaction_id = NEW.transaction_id AND c.school_id = NEW.school_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    SELECT coalesce(sum(i.quantity * i.unit_price_cents), 0), count(*),
           count(*) FILTER (WHERE i.campaign_id IS DISTINCT FROM v_campaign)
    INTO v_sum, v_lines, v_foreign
    FROM public.contribution_items i
    WHERE i.transaction_id = NEW.transaction_id AND i.school_id = NEW.school_id;
    IF v_campaign IS NULL THEN
        IF v_lines > 0 THEN
            RAISE EXCEPTION 'only the contribution of a campaign has items'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF v_lines = 0 OR v_foreign > 0 OR v_sum <> v_amount THEN
        RAISE EXCEPTION 'the amount of the contribution of a campaign is the sum of its items'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END
$body$
""",
}


def _literal(values: Sequence[str]) -> str:
    return ", ".join("'" + value + "'" for value in values)


def _trigger(
    table: str,
    name: str,
    timing: str,
    function: str,
    *args: str,
    statement: bool = False,
    deferred: bool = False,
    when: str | None = None,
) -> str:
    kind = "CONSTRAINT TRIGGER" if deferred else "TRIGGER"
    defer = "DEFERRABLE INITIALLY DEFERRED " if deferred else ""
    each = "FOR EACH STATEMENT" if statement else "FOR EACH ROW"
    condition = f" WHEN ({when})" if when else ""
    return (
        f"CREATE {kind} {name} {timing} ON public.{table} {defer}{each}{condition} "
        f"EXECUTE FUNCTION public.{function}({_literal(args)})"
    )


def _image_columns(prefix: str) -> str:
    # All five or none: a row never points at half an image.
    return f"""
            {prefix}_storage_key text,
            {prefix}_content_type text,
            {prefix}_size_bytes bigint,
            {prefix}_sha256 text,
            {prefix}_version integer NOT NULL DEFAULT 0"""


def _image_checks(table: str, prefix: str) -> str:
    return f"""
            CONSTRAINT ck_{table}_{prefix}_all_or_none CHECK (
                ({prefix}_storage_key IS NULL) = ({prefix}_content_type IS NULL)
                AND ({prefix}_storage_key IS NULL) = ({prefix}_size_bytes IS NULL)
                AND ({prefix}_storage_key IS NULL) = ({prefix}_sha256 IS NULL)),
            CONSTRAINT ck_{table}_{prefix}_key_length CHECK (
                {prefix}_storage_key IS NULL
                OR (length({prefix}_storage_key) BETWEEN 1 AND 500 AND {prefix}_storage_key !~ '^/')),
            CONSTRAINT ck_{table}_{prefix}_content_type_image CHECK (
                {prefix}_content_type IS NULL OR {prefix}_content_type IN ({IMAGE_TYPES})),
            CONSTRAINT ck_{table}_{prefix}_size_range CHECK (
                {prefix}_size_bytes IS NULL OR {prefix}_size_bytes BETWEEN 1 AND 5242880),
            CONSTRAINT ck_{table}_{prefix}_sha256_format CHECK (
                {prefix}_sha256 IS NULL OR {prefix}_sha256 ~ '{HEX64}'),
            CONSTRAINT ck_{table}_{prefix}_version_range CHECK ({prefix}_version >= 0)"""


def _create_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE campaigns (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            created_by_user_id uuid NOT NULL,
            title text NOT NULL,
            description text,
            status text NOT NULL DEFAULT 'DRAFT',
            starts_on date,
            ends_on date,
            ended_at timestamptz,{_image_columns("cover")},
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_campaigns PRIMARY KEY (id),
            CONSTRAINT fk_campaigns_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_campaigns_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_campaigns_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            -- Target of the composite foreign keys of the products and of the contributions.
            CONSTRAINT uq_campaigns_id_organization_id_school_id
                UNIQUE (id, organization_id, school_id),
            CONSTRAINT ck_campaigns_status_valid CHECK (status IN ({STATUSES})),
            CONSTRAINT ck_campaigns_title_length CHECK (length(btrim(title)) BETWEEN 1 AND 120),
            CONSTRAINT ck_campaigns_description_length
                CHECK (description IS NULL OR length(description) <= 2000),
            CONSTRAINT ck_campaigns_dates_in_order
                CHECK (starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on),
            CONSTRAINT ck_campaigns_ended_iff_status CHECK ((status = 'ENDED') = (ended_at IS NOT NULL)),{_image_checks("campaigns", "cover")}
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_campaigns_school_id_status ON campaigns (school_id, status, created_at DESC)"
    )
    op.execute(
        f"""
        CREATE TABLE campaign_items (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            campaign_id uuid NOT NULL,
            name text NOT NULL,
            description text,
            price_cents bigint NOT NULL,
            max_per_order integer,
            position integer NOT NULL DEFAULT 0,
            is_active boolean NOT NULL DEFAULT true,{_image_columns("image")},
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_campaign_items PRIMARY KEY (id),
            CONSTRAINT fk_campaign_items_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_campaign_items_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_campaign_items_campaign_id_campaigns
                FOREIGN KEY (campaign_id, organization_id, school_id)
                REFERENCES campaigns (id, organization_id, school_id) ON DELETE RESTRICT,
            -- Target of the composite foreign key of what an order bought.
            CONSTRAINT uq_campaign_items_id_campaign_id_organization_id_school_id
                UNIQUE (id, campaign_id, organization_id, school_id),
            CONSTRAINT ck_campaign_items_name_length CHECK (length(btrim(name)) BETWEEN 1 AND 120),
            CONSTRAINT ck_campaign_items_description_length
                CHECK (description IS NULL OR length(description) <= 500),
            CONSTRAINT ck_campaign_items_price_range CHECK (price_cents BETWEEN 100 AND 1000000),
            CONSTRAINT ck_campaign_items_max_per_order_range
                CHECK (max_per_order IS NULL OR max_per_order BETWEEN 1 AND 99),
            CONSTRAINT ck_campaign_items_position_range CHECK (position BETWEEN 0 AND 999),{_image_checks("campaign_items", "image")}
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_campaign_items_campaign_id ON campaign_items (campaign_id, position)"
    )
    op.execute("CREATE INDEX ix_campaign_items_school_id ON campaign_items (school_id)")

    # The tie of a contribution to its campaign, written with the row and never changed.
    op.execute("ALTER TABLE contributions ADD COLUMN campaign_id uuid")
    op.execute(
        "ALTER TABLE contributions ADD CONSTRAINT "
        "fk_contributions_campaign_id_campaigns "
        "FOREIGN KEY (campaign_id, organization_id, school_id) "
        "REFERENCES campaigns (id, organization_id, school_id) ON DELETE RESTRICT"
    )
    op.execute("CREATE INDEX ix_contributions_campaign_id ON contributions (campaign_id)")

    op.execute(
        """
        CREATE TABLE contribution_items (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            transaction_id uuid NOT NULL,
            campaign_id uuid NOT NULL,
            campaign_item_id uuid NOT NULL,
            item_name text NOT NULL,
            unit_price_cents bigint NOT NULL,
            quantity integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_contribution_items PRIMARY KEY (id),
            CONSTRAINT fk_contribution_items_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_contribution_items_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_contribution_items_transaction_id_contributions
                FOREIGN KEY (transaction_id, organization_id, school_id)
                REFERENCES contributions (transaction_id, organization_id, school_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_contribution_items_campaign_item_id_campaign_items
                FOREIGN KEY (campaign_item_id, campaign_id, organization_id, school_id)
                REFERENCES campaign_items (id, campaign_id, organization_id, school_id)
                ON DELETE RESTRICT,
            -- A product appears once per order (the quantity says how many).
            CONSTRAINT uq_contribution_items_school_id_transaction_id_campaign_item_id
                UNIQUE (school_id, transaction_id, campaign_item_id),
            CONSTRAINT ck_contribution_items_item_name_length
                CHECK (length(btrim(item_name)) BETWEEN 1 AND 120),
            CONSTRAINT ck_contribution_items_unit_price_range
                CHECK (unit_price_cents BETWEEN 100 AND 1000000),
            CONSTRAINT ck_contribution_items_quantity_range CHECK (quantity BETWEEN 1 AND 99)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_contribution_items_transaction_id ON contribution_items (transaction_id)"
    )
    op.execute(
        "CREATE INDEX ix_contribution_items_campaign_item_id ON contribution_items (campaign_item_id)"
    )
    op.execute("CREATE INDEX ix_contribution_items_school_id ON contribution_items (school_id)")


def _create_triggers() -> None:
    for body in FUNCTIONS.values():
        op.execute(body)
    names = ", ".join(f"'{name}'" for name in FUNCTIONS)
    op.execute(
        f"""
        DO $$
        DECLARE
            f record;
        BEGIN
            FOR f IN
                SELECT p.oid::regprocedure AS signature FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname = ANY (ARRAY[{names}])
            LOOP
                EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f.signature);
            END LOOP;
        END
        $$
        """
    )
    statements = [
        _trigger(
            "campaigns",
            "campaigns_05_immutable",
            "BEFORE UPDATE",
            "assert_immutable_columns",
            "id",
            "organization_id",
            "school_id",
            "created_by_user_id",
            "created_at",
        ),
        _trigger("campaigns", "campaigns_06_freeze", "BEFORE UPDATE", "freeze_when_final", "ENDED"),
        _trigger("campaigns", "campaigns_07_change", "BEFORE UPDATE", "campaigns_check_change"),
        _trigger(
            "campaigns",
            "campaigns_10_set_once",
            "BEFORE UPDATE",
            "assert_set_once_columns",
            "ended_at",
        ),
        _trigger(
            "campaigns",
            "campaigns_25_member",
            "BEFORE INSERT",
            "assert_active_member",
            "created_by_user_id",
        ),
        _trigger(
            "campaigns",
            "campaigns_95_audit",
            "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,created_by_user_id,status,starts_on,ends_on,ended_at,"
            "cover_content_type,cover_size_bytes,cover_sha256,cover_version",
            "title,description,cover_storage_key",
            "id",
            "",
        ),
        _trigger(
            "campaign_items",
            "campaign_items_05_immutable",
            "BEFORE UPDATE",
            "assert_immutable_columns",
            "id",
            "organization_id",
            "school_id",
            "campaign_id",
            "created_at",
        ),
        _trigger(
            "campaign_items",
            "campaign_items_20_state",
            "BEFORE INSERT OR UPDATE",
            "campaign_items_check_state",
        ),
        _trigger(
            "campaign_items",
            "campaign_items_95_audit",
            "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,campaign_id,price_cents,max_per_order,position,"
            "is_active,image_content_type,image_size_bytes,image_sha256,image_version",
            "name,description,image_storage_key",
            "id",
            "",
        ),
        _trigger(
            "contribution_items",
            "contribution_items_05_no_update",
            "BEFORE UPDATE",
            "forbid_update",
        ),
        _trigger(
            "contribution_items",
            "contribution_items_20_item",
            "BEFORE INSERT",
            "contribution_items_check_item",
        ),
        _trigger(
            "contribution_items",
            "contribution_items_90_total",
            "AFTER INSERT",
            "contribution_items_check_total",
            deferred=True,
        ),
        _trigger(
            "contribution_items",
            "contribution_items_95_audit",
            "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,transaction_id,campaign_id,campaign_item_id,"
            "unit_price_cents,quantity",
            "item_name",
            "id",
            "",
        ),
        # A contribution of a campaign with no item at all never fires the trigger of the items:
        # this one catches it.
        _trigger(
            "contributions",
            "contributions_90_campaign_total",
            "AFTER INSERT",
            "contribution_items_check_total",
            deferred=True,
            when="NEW.campaign_id IS NOT NULL",
        ),
    ]
    for table in TABLES:
        statements.append(_trigger(table, f"{table}_no_delete", "BEFORE DELETE", "forbid_delete"))
        statements.append(
            _trigger(
                table, f"{table}_no_truncate", "BEFORE TRUNCATE", "forbid_truncate", statement=True
            )
        )
    for statement in statements:
        op.execute(statement)
    # campaign_id joins the columns of a contribution that never change.
    op.execute("DROP TRIGGER contributions_05_immutable ON public.contributions")
    op.execute(
        "CREATE TRIGGER contributions_05_immutable BEFORE UPDATE ON public.contributions "
        f"FOR EACH ROW EXECUTE FUNCTION public.assert_immutable_columns({_literal(IMMUTABLE_AFTER)})"
    )


def _enable_rls_and_grant() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({SCOPE})")
        op.execute(
            f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({_write_check(table)})"
        )
    for table in ("campaigns", "campaign_items"):
        op.execute(
            f"CREATE POLICY {table}_update ON {table} FOR UPDATE "
            f"USING ({SCOPE}) WITH CHECK ({_write_check(table)})"
        )
    # No DELETE policy and no DELETE grant. The id, the status and the timestamps of a new row are
    # the database's (the defaults), not the caller's.
    op.execute("GRANT SELECT ON campaigns, campaign_items, contribution_items TO apm_app")
    op.execute(
        "GRANT INSERT (organization_id, school_id, created_by_user_id, title, description, "
        "starts_on, ends_on) ON campaigns TO apm_app"
    )
    op.execute(
        "GRANT UPDATE (title, description, status, starts_on, ends_on, ended_at, cover_storage_key, "
        "cover_content_type, cover_size_bytes, cover_sha256, cover_version, updated_at) "
        "ON campaigns TO apm_app"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, campaign_id, name, description, price_cents, "
        "max_per_order, position) ON campaign_items TO apm_app"
    )
    op.execute(
        "GRANT UPDATE (name, description, price_cents, max_per_order, position, is_active, "
        "image_storage_key, image_content_type, image_size_bytes, image_sha256, image_version, "
        "updated_at) ON campaign_items TO apm_app"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, transaction_id, campaign_id, campaign_item_id, "
        "item_name, unit_price_cents, quantity) ON contribution_items TO apm_app"
    )
    op.execute("GRANT SELECT (campaign_id), INSERT (campaign_id) ON contributions TO apm_app")


def _category_function(with_campaigns: bool = True) -> str:
    rows = (*CATEGORIES, CAMPAIGN_CATEGORY) if with_campaigns else CATEGORIES
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
    _create_tables()
    _create_triggers()
    _enable_rls_and_grant()
    # New schools get the category from the trigger of the school...
    op.execute(_category_function())
    op.execute("RESET ROLE")
    # ...and the schools that already exist get it now. Like the backfills of 0007 and 0011 this
    # runs as the admin: with an admin that row level security hides the categories from, nothing is
    # inserted and the campaign flow answers "payment_unavailable" until the category exists.
    key, name, applies_to, report_group = CAMPAIGN_CATEGORY
    op.execute(
        "INSERT INTO categories (organization_id, school_id, key, name, applies_to, report_group, "
        "requires_approval) "
        f"SELECT s.organization_id, s.id, '{key}', '{name}', '{applies_to}', '{report_group}', true "
        "FROM schools s ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    # Everything this revision created goes, the campaigns, their products and what the orders
    # bought included (the image files stay on the volume: they are not in the database). The
    # category stays: a ledger row may already be filed under it, and an unused default is harmless.
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TRIGGER contributions_90_campaign_total ON public.contributions")
    op.execute("DROP TRIGGER contributions_05_immutable ON public.contributions")
    # Children first: the items point at the contributions and at the products, the contributions
    # at the campaigns.
    op.execute("DROP TABLE IF EXISTS contribution_items")
    op.execute("DROP INDEX IF EXISTS ix_contributions_campaign_id")
    op.execute(
        "ALTER TABLE contributions DROP CONSTRAINT IF EXISTS fk_contributions_campaign_id_campaigns"
    )
    op.execute("ALTER TABLE contributions DROP COLUMN IF EXISTS campaign_id")
    op.execute("DROP TABLE IF EXISTS campaign_items")
    op.execute("DROP TABLE IF EXISTS campaigns")
    op.execute(
        "CREATE TRIGGER contributions_05_immutable BEFORE UPDATE ON public.contributions "
        f"FOR EACH ROW EXECUTE FUNCTION public.assert_immutable_columns({_literal(IMMUTABLE_BEFORE)})"
    )
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{name}()")
    op.execute(_category_function(with_campaigns=False))
    op.execute("RESET ROLE")
