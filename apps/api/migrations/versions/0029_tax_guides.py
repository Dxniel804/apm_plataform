"""tax guides: the retentions on services the APM pays, and the data to fill a guide by hand

Revision ID: 0029_tax_guides
Revises: 0028_pdde
Create Date: 2026-10-19

When the APM pays a service it may have to hold back a tax (income tax, INSS, ISS) and pay it to the
government. The product does NOT talk to the government and does NOT decide the law: it keeps the
retentions, adds them up by tax and month, and shows what to type in the public site of the
Receita Federal ("cola de prova": value, code, due date). What is in this revision:

* `tax_rules`: how a retention is worked out (the rate, a cap for the base, the code of the guide, the
  due day) written by the school, usually with its accountant. **The product ships no rate and no
  due date as if they were true**: a rule starts as typed, and only counts as validated when somebody
  ticks that the accountant confirmed it (`validated_at`, who and when). Insert-only: a change is a new
  row of the same `rule_key`, and the latest one counts; each retention remembers the exact row it
  used, so what was calculated never changes under it.
* `tax_retentions`: one row per service paid with a retention (who is paid: a person or a company, the
  name, the competence month, the gross amount, what was retained). Voided, never deleted.
  It does not touch the ledger: paying the guide is an expense like any other.
* A default expense purpose, "Impostos retidos e tributos pagos" (`tax_payments`), for that payment.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_tax_guides"
down_revision: str | None = "0028_pdde"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
RULES = "tax_rules"
RETENTIONS = "tax_retentions"
TABLES = (RULES, RETENTIONS)

# The default purposes of a school: the list of 0027 plus the payment of the taxes.
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
TAX_PAYMENTS = (
    "tax_payments",
    "Impostos retidos e tributos pagos",
    "OUT",
    "EXPENSES_REIMBURSEMENTS",
)

FUNCTIONS = {
    "tax_retentions_check": f"""
CREATE FUNCTION public.tax_retentions_check() RETURNS trigger {HEADER} AS $body$
DECLARE
    v_applies text;
BEGIN
    SELECT r.applies_to INTO v_applies
    FROM public.tax_rules r
    WHERE r.id = NEW.rule_id AND r.school_id = NEW.school_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'the rule belongs to another school' USING ERRCODE = 'check_violation';
    END IF;
    IF v_applies <> 'BOTH' AND v_applies <> NEW.provider_kind THEN
        RAISE EXCEPTION 'the rule does not apply to this kind of provider'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
}


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


def _write_check(table: str) -> str:
    return (
        f"({SCOPE} AND EXISTS (SELECT 1 FROM public.schools s "
        f"WHERE s.id = {table}.school_id AND s.organization_id = {table}.organization_id))"
    )


def _tenant_fks(table: str) -> str:
    return (
        f"CONSTRAINT fk_{table}_organization_id_organizations "
        "FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT, "
        f"CONSTRAINT fk_{table}_school_id_organization_id_schools "
        "FOREIGN KEY (school_id, organization_id) REFERENCES schools (id, organization_id) "
        "ON DELETE RESTRICT"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(_category_function((*CATEGORIES, TAX_PAYMENTS)))
    for name, function in FUNCTIONS.items():
        op.execute(function)
        op.execute(f"REVOKE ALL ON FUNCTION public.{name}() FROM PUBLIC")
    op.execute(
        f"""
        CREATE TABLE {RULES} (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            rule_key text NOT NULL,
            label text NOT NULL,
            tax_kind text NOT NULL,
            applies_to text NOT NULL,
            rate_bps integer NOT NULL,
            base_cap_cents bigint,
            min_total_cents bigint NOT NULL DEFAULT 1000,
            darf_code text,
            howto text,
            due_day smallint NOT NULL,
            due_roll text NOT NULL,
            source_note text,
            validated_at timestamptz,
            validated_by_user_id uuid,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_{RULES} PRIMARY KEY (id),
            {_tenant_fks(RULES)},
            CONSTRAINT fk_{RULES}_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT fk_{RULES}_validated_by_user_id_users
                FOREIGN KEY (validated_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_{RULES}_id_school_id UNIQUE (id, school_id),
            CONSTRAINT ck_{RULES}_key_format CHECK (rule_key ~ '^[a-z0-9][a-z0-9-]{{2,39}}$'),
            CONSTRAINT ck_{RULES}_label_length CHECK (length(btrim(label)) BETWEEN 1 AND 80),
            CONSTRAINT ck_{RULES}_kind_valid CHECK (tax_kind IN ('IRRF', 'INSS', 'ISS', 'OTHER')),
            CONSTRAINT ck_{RULES}_applies_valid CHECK (applies_to IN ('PF', 'PJ', 'BOTH')),
            CONSTRAINT ck_{RULES}_rate_range CHECK (rate_bps BETWEEN 1 AND 10000),
            CONSTRAINT ck_{RULES}_cap_range
                CHECK (base_cap_cents IS NULL OR base_cap_cents BETWEEN 1 AND 100000000000),
            CONSTRAINT ck_{RULES}_min_range CHECK (min_total_cents BETWEEN 0 AND 100000000),
            CONSTRAINT ck_{RULES}_code_format CHECK (darf_code IS NULL OR darf_code ~ '^[0-9]{{4}}$'),
            CONSTRAINT ck_{RULES}_howto_length
                CHECK (howto IS NULL OR length(btrim(howto)) BETWEEN 1 AND 300),
            -- A guide is paid with a code at the Receita, or the rule says how else (the city, the
            -- DCTFWeb): never neither.
            CONSTRAINT ck_{RULES}_where_to_pay CHECK (darf_code IS NOT NULL OR howto IS NOT NULL),
            CONSTRAINT ck_{RULES}_due_day_range CHECK (due_day BETWEEN 1 AND 31),
            CONSTRAINT ck_{RULES}_due_roll_valid CHECK (due_roll IN ('PREVIOUS', 'NEXT')),
            CONSTRAINT ck_{RULES}_source_length
                CHECK (source_note IS NULL OR length(btrim(source_note)) BETWEEN 1 AND 200),
            CONSTRAINT ck_{RULES}_validated_pair
                CHECK ((validated_at IS NULL) = (validated_by_user_id IS NULL))
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_{RULES}_school_key ON {RULES} (school_id, rule_key, created_at DESC)"
    )
    op.execute(
        f"""
        CREATE TABLE {RETENTIONS} (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            rule_id uuid NOT NULL,
            provider_kind text NOT NULL,
            provider_name text NOT NULL,
            competence date NOT NULL,
            gross_cents bigint NOT NULL,
            base_cents bigint NOT NULL,
            retained_cents bigint NOT NULL,
            rate_bps integer NOT NULL,
            note text,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            voided_at timestamptz,
            voided_by_user_id uuid,
            CONSTRAINT pk_{RETENTIONS} PRIMARY KEY (id),
            {_tenant_fks(RETENTIONS)},
            -- The rule is one of the SAME school (the composite key), so a retention never borrows another's.
            CONSTRAINT fk_{RETENTIONS}_rule_id_{RULES}
                FOREIGN KEY (rule_id, school_id) REFERENCES {RULES} (id, school_id) ON DELETE RESTRICT,
            CONSTRAINT fk_{RETENTIONS}_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT fk_{RETENTIONS}_voided_by_user_id_users
                FOREIGN KEY (voided_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_{RETENTIONS}_kind_valid CHECK (provider_kind IN ('PF', 'PJ')),
            CONSTRAINT ck_{RETENTIONS}_name_length CHECK (length(btrim(provider_name)) BETWEEN 1 AND 120),
            CONSTRAINT ck_{RETENTIONS}_competence_first_day CHECK (extract(day FROM competence) = 1),
            CONSTRAINT ck_{RETENTIONS}_amounts CHECK (
                gross_cents BETWEEN 1 AND 100000000000
                AND base_cents BETWEEN 1 AND gross_cents
                AND retained_cents BETWEEN 0 AND base_cents),
            CONSTRAINT ck_{RETENTIONS}_rate_range CHECK (rate_bps BETWEEN 1 AND 10000),
            CONSTRAINT ck_{RETENTIONS}_note_length CHECK (note IS NULL OR length(note) <= 300),
            CONSTRAINT ck_{RETENTIONS}_void_pair
                CHECK ((voided_at IS NULL) = (voided_by_user_id IS NULL))
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_{RETENTIONS}_school_competence ON {RETENTIONS} (school_id, competence)"
    )

    def trig(table: str, name: str, timing: str, fn: str, *args: str, each: str = "ROW") -> None:
        literal = ", ".join("'" + a + "'" for a in args)
        op.execute(
            f"CREATE TRIGGER {name} {timing} ON public.{table} "
            f"FOR EACH {each} EXECUTE FUNCTION public.{fn}({literal})"
        )

    trig(RULES, f"{RULES}_05_no_update", "BEFORE UPDATE", "forbid_update")
    trig(RULES, f"{RULES}_25_member", "BEFORE INSERT", "assert_active_member", "created_by_user_id")
    trig(
        RULES,
        f"{RULES}_95_audit",
        "AFTER INSERT OR UPDATE",
        "audit_row_change",
        "id,organization_id,school_id,rule_key,tax_kind,applies_to,rate_bps,base_cap_cents,"
        "min_total_cents,darf_code,due_day,due_roll,validated_at",
        "label,howto,source_note",
        "id",
        "",
    )
    trig(
        RETENTIONS,
        f"{RETENTIONS}_05_immutable",
        "BEFORE UPDATE",
        "assert_immutable_columns",
        "id", "organization_id", "school_id", "rule_id", "provider_kind", "provider_name",
        "competence", "gross_cents", "base_cents", "retained_cents", "rate_bps", "note",
        "created_by_user_id", "created_at",
    )  # fmt: skip
    trig(RETENTIONS, f"{RETENTIONS}_20_check", "BEFORE INSERT", "tax_retentions_check")
    trig(
        RETENTIONS,
        f"{RETENTIONS}_25_member",
        "BEFORE INSERT",
        "assert_active_member",
        "created_by_user_id",
    )
    trig(
        RETENTIONS,
        f"{RETENTIONS}_95_audit",
        "AFTER INSERT OR UPDATE",
        "audit_row_change",
        "id,organization_id,school_id,rule_id,provider_kind,competence,gross_cents,base_cents,"
        "retained_cents,voided_at",
        "provider_name,note",
        "id",
        "",
    )
    for table in TABLES:
        trig(table, f"{table}_no_delete", "BEFORE DELETE", "forbid_delete")
        trig(table, f"{table}_no_truncate", "BEFORE TRUNCATE", "forbid_truncate", each="STATEMENT")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({SCOPE})")
        op.execute(
            f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({_write_check(table)})"
        )
        op.execute(f"GRANT SELECT ON {table} TO apm_app")
    op.execute(
        f"CREATE POLICY {RETENTIONS}_update ON {RETENTIONS} FOR UPDATE USING ({SCOPE}) "
        f"WITH CHECK ({_write_check(RETENTIONS)})"
    )
    op.execute(
        f"GRANT INSERT (organization_id, school_id, rule_key, label, tax_kind, applies_to, rate_bps, "
        f"base_cap_cents, min_total_cents, darf_code, howto, due_day, due_roll, source_note, "
        f"validated_at, validated_by_user_id, created_by_user_id) ON {RULES} TO apm_app"
    )
    op.execute(
        f"GRANT INSERT (organization_id, school_id, rule_id, provider_kind, provider_name, "
        f"competence, gross_cents, base_cents, retained_cents, rate_bps, note, created_by_user_id) "
        f"ON {RETENTIONS} TO apm_app"
    )
    op.execute(f"GRANT UPDATE (voided_at, voided_by_user_id) ON {RETENTIONS} TO apm_app")
    op.execute("RESET ROLE")
    key, name, applies_to, report_group = TAX_PAYMENTS
    op.execute(
        "INSERT INTO categories (organization_id, school_id, key, name, applies_to, report_group, "
        "requires_approval) "
        f"SELECT s.organization_id, s.id, '{key}', '{name}', '{applies_to}', '{report_group}', true "
        "FROM schools s ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    # The tables go (with what was typed in them). The purpose stays: a ledger row may be filed under it.
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(f"DROP TABLE IF EXISTS {RETENTIONS}")
    op.execute(f"DROP TABLE IF EXISTS {RULES}")
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{name}()")
    op.execute(_category_function(CATEGORIES))
    op.execute("RESET ROLE")
