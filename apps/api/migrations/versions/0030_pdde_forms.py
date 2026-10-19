"""PDDE official forms: the data the FNDE forms ask for and the PDDE did not keep yet

Revision ID: 0030_pdde_forms
Revises: 0029_tax_guides
Create Date: 2026-10-19

The FNDE publishes the forms of the accountability (Demonstrativo da execução da receita e da despesa e de
pagamentos efetuados, Relação de bens, Conciliação bancária). To fill the first one from what the school
already typed, this revision keeps what was missing, with the same rules as the rest of the PDDE layer
(insert-only, row level security, audit that never copies free text, nothing deleted):

* `pdde_entities`: the identification of the entity (name as in the CNPJ card, CNPJ, address, city, state) printed in block 1 of
  every form. Insert-only; the latest row counts.
* `pdde_carryovers`: the balance that came from the previous year (field 08), by program and by custeio
  and capital, typed by the school when it did not start the year inside the system. Insert-only.
* `pdde_documents`: the CNPJ or CPF of whoever was paid (field 21), and, for the goods of capital, the
  quantity and the specification (the Relação de bens). A document never changes after it is written,
  except for being voided.
* `pdde_classifications`: the number of the check or of the bank order (field 26), and two more kinds of
  line: the yield of the financial investment (money in, field 11) and the return of money to the FNDE
  (money out, field 12).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_pdde_forms"
down_revision: str | None = "0029_tax_guides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
ENTITIES = "pdde_entities"
CARRYOVERS = "pdde_carryovers"
TABLES = (ENTITIES, CARRYOVERS)

DOCUMENT_COLUMNS = (
    "id", "organization_id", "school_id", "line_id", "doc_kind", "access_key", "doc_number",
    "issued_on", "vendor", "amount_cents", "stamped", "created_by_user_id", "created_at",
)  # fmt: skip
NEW_DOCUMENT_COLUMNS = ("vendor_tax_id", "quantity", "specification")

CLASSIFICATION_CHECK = f"""
CREATE OR REPLACE FUNCTION public.pdde_classifications_check() RETURNS trigger {HEADER} AS $body$
DECLARE
    v_amount bigint;
    v_purpose text;
BEGIN
    SELECT l.amount_cents, a.purpose INTO v_amount, v_purpose
    FROM public.bank_statement_lines l
    JOIN public.bank_accounts a ON a.id = l.bank_account_id
    WHERE l.id = NEW.line_id AND l.school_id = NEW.school_id
      AND l.organization_id = NEW.organization_id;
    IF NOT FOUND OR v_purpose <> 'PDDE' THEN
        RAISE EXCEPTION 'only a line of a PDDE account is classified'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind IN ('TRANSFER', 'YIELD') AND v_amount <= 0 THEN
        RAISE EXCEPTION 'a transfer or a yield is money in' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind IN ('EXPENSE', 'RETURN_TO_FNDE') AND v_amount >= 0 THEN
        RAISE EXCEPTION 'an expense or a return to the FNDE is money out'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
"""
CLASSIFICATION_CHECK_OLD = CLASSIFICATION_CHECK.replace(
    "IF NEW.kind IN ('TRANSFER', 'YIELD') AND v_amount <= 0",
    "IF NEW.kind = 'TRANSFER' AND v_amount <= 0",
).replace(
    "IF NEW.kind IN ('EXPENSE', 'RETURN_TO_FNDE') AND v_amount >= 0",
    "IF NEW.kind = 'EXPENSE' AND v_amount >= 0",
)

KINDS_NEW = "'TRANSFER', 'YIELD', 'EXPENSE', 'RETURN_TO_FNDE', 'TAX_TO_EEX', 'REFUND', 'INELIGIBLE'"
KINDS_OLD = "'TRANSFER', 'EXPENSE', 'TAX_TO_EEX', 'REFUND', 'INELIGIBLE'"
SHAPE_NEW = """
    (kind = 'TRANSFER' AND program IS NOT NULL AND object IS NULL)
    OR (kind IN ('YIELD', 'RETURN_TO_FNDE') AND program IS NOT NULL AND economic_category IS NOT NULL
        AND object IS NULL)
    OR (kind = 'EXPENSE' AND program IS NOT NULL AND economic_category IS NOT NULL AND object IS NOT NULL)
    OR kind IN ('TAX_TO_EEX', 'REFUND', 'INELIGIBLE')
"""
SHAPE_OLD = """
    (kind = 'TRANSFER' AND program IS NOT NULL AND object IS NULL)
    OR (kind = 'EXPENSE' AND program IS NOT NULL AND economic_category IS NOT NULL AND object IS NOT NULL)
    OR kind IN ('TAX_TO_EEX', 'REFUND', 'INELIGIBLE')
"""

CLASSIFICATION_AUDIT_NEW = (
    "CREATE TRIGGER pdde_classifications_95_audit AFTER INSERT OR UPDATE ON public.pdde_classifications "
    "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
    "'id,organization_id,school_id,line_id,kind,program,economic_category', "
    "'program_label,object,note,payment_number', 'id', '')"
)
CLASSIFICATION_AUDIT_OLD = (
    "CREATE TRIGGER pdde_classifications_95_audit AFTER INSERT OR UPDATE ON public.pdde_classifications "
    "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
    "'id,organization_id,school_id,line_id,kind,program,economic_category', "
    "'program_label,object,note', 'id', '')"
)


def _literal(values: Sequence[str]) -> str:
    return ", ".join("'" + value + "'" for value in values)


def _document_triggers(extra: Sequence[str], flagged: str) -> list[str]:
    return [
        "CREATE TRIGGER pdde_documents_05_immutable BEFORE UPDATE ON public.pdde_documents "
        "FOR EACH ROW EXECUTE FUNCTION public.assert_immutable_columns("
        f"{_literal([*DOCUMENT_COLUMNS, *extra])})",
        "CREATE TRIGGER pdde_documents_95_audit AFTER INSERT OR UPDATE ON public.pdde_documents "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_row_change("
        "'id,organization_id,school_id,line_id,doc_kind,amount_cents,issued_on,stamped,voided_at', "
        f"'{flagged}', 'id', '')",
    ]


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
        "ON DELETE RESTRICT, "
        f"CONSTRAINT fk_{table}_created_by_user_id_users "
        "FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")

    # --- the documents: who was paid, and what was bought ------------------------------------------
    op.execute("ALTER TABLE pdde_documents ADD COLUMN vendor_tax_id text")
    op.execute("ALTER TABLE pdde_documents ADD COLUMN quantity integer")
    op.execute("ALTER TABLE pdde_documents ADD COLUMN specification text")
    op.execute(
        "ALTER TABLE pdde_documents ADD CONSTRAINT ck_pdde_documents_vendor_tax_id_format "
        "CHECK (vendor_tax_id IS NULL OR vendor_tax_id ~ '^([0-9]{11}|[0-9]{14})$')"
    )
    op.execute(
        "ALTER TABLE pdde_documents ADD CONSTRAINT ck_pdde_documents_quantity_range "
        "CHECK (quantity IS NULL OR quantity BETWEEN 1 AND 1000000)"
    )
    op.execute(
        "ALTER TABLE pdde_documents ADD CONSTRAINT ck_pdde_documents_specification_length "
        "CHECK (specification IS NULL OR length(btrim(specification)) BETWEEN 1 AND 200)"
    )
    op.execute("GRANT INSERT (vendor_tax_id, quantity, specification) ON pdde_documents TO apm_app")
    op.execute("DROP TRIGGER pdde_documents_05_immutable ON public.pdde_documents")
    op.execute("DROP TRIGGER pdde_documents_95_audit ON public.pdde_documents")
    for statement in _document_triggers(
        NEW_DOCUMENT_COLUMNS, "access_key,doc_number,vendor,vendor_tax_id,specification"
    ):
        op.execute(statement)

    # --- the classifications: the payment number, the yield and the return -------------------------
    op.execute("ALTER TABLE pdde_classifications ADD COLUMN payment_number text")
    op.execute(
        "ALTER TABLE pdde_classifications ADD CONSTRAINT ck_pdde_classifications_payment_number_length "
        "CHECK (payment_number IS NULL OR length(btrim(payment_number)) BETWEEN 1 AND 40)"
    )
    op.execute("GRANT INSERT (payment_number) ON pdde_classifications TO apm_app")
    op.execute(
        "ALTER TABLE pdde_classifications DROP CONSTRAINT ck_pdde_classifications_kind_valid"
    )
    op.execute(
        f"ALTER TABLE pdde_classifications ADD CONSTRAINT ck_pdde_classifications_kind_valid CHECK (kind IN ({KINDS_NEW}))"
    )
    op.execute("ALTER TABLE pdde_classifications DROP CONSTRAINT ck_pdde_classifications_shape")
    op.execute(
        f"ALTER TABLE pdde_classifications ADD CONSTRAINT ck_pdde_classifications_shape CHECK ({SHAPE_NEW})"
    )
    op.execute(CLASSIFICATION_CHECK)
    op.execute("DROP TRIGGER pdde_classifications_95_audit ON public.pdde_classifications")
    op.execute(CLASSIFICATION_AUDIT_NEW)

    # --- the entity and the carry-over ---------------------------------------------------------------
    op.execute(
        f"""
        CREATE TABLE {ENTITIES} (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            legal_name text NOT NULL,
            cnpj text NOT NULL,
            address text NOT NULL,
            city text NOT NULL,
            state text NOT NULL,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_{ENTITIES} PRIMARY KEY (id),
            {_tenant_fks(ENTITIES)},
            CONSTRAINT ck_{ENTITIES}_legal_name_length CHECK (length(btrim(legal_name)) BETWEEN 1 AND 120),
            CONSTRAINT ck_{ENTITIES}_cnpj_format CHECK (cnpj ~ '^[0-9]{{14}}$'),
            CONSTRAINT ck_{ENTITIES}_address_length CHECK (length(btrim(address)) BETWEEN 1 AND 200),
            CONSTRAINT ck_{ENTITIES}_city_length CHECK (length(btrim(city)) BETWEEN 1 AND 80),
            CONSTRAINT ck_{ENTITIES}_state_format CHECK (state ~ '^[A-Z]{{2}}$')
        )
        """
    )
    op.execute(f"CREATE INDEX ix_{ENTITIES}_school_id ON {ENTITIES} (school_id, created_at DESC)")
    op.execute(
        f"""
        CREATE TABLE {CARRYOVERS} (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            year smallint NOT NULL,
            program text NOT NULL,
            program_label text,
            custeio_cents bigint NOT NULL,
            capital_cents bigint NOT NULL,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_{CARRYOVERS} PRIMARY KEY (id),
            {_tenant_fks(CARRYOVERS)},
            CONSTRAINT ck_{CARRYOVERS}_year_range CHECK (year BETWEEN 2000 AND 2100),
            CONSTRAINT ck_{CARRYOVERS}_program_valid
                CHECK (program IN ('BASICO', 'EQUIDADE', 'QUALIDADE', 'CONECTADO', 'OUTRO')),
            CONSTRAINT ck_{CARRYOVERS}_label_shape CHECK (
                (program = 'OUTRO') = (program_label IS NOT NULL)
                AND (program_label IS NULL OR length(btrim(program_label)) BETWEEN 1 AND 60)),
            CONSTRAINT ck_{CARRYOVERS}_amounts
                CHECK (custeio_cents BETWEEN 0 AND 100000000000 AND capital_cents BETWEEN 0 AND 100000000000)
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_{CARRYOVERS}_school_year ON {CARRYOVERS} (school_id, year, program, created_at DESC)"
    )

    def trig(table: str, name: str, timing: str, fn: str, *args: str, each: str = "ROW") -> None:
        literal = ", ".join("'" + a + "'" for a in args)
        op.execute(
            f"CREATE TRIGGER {name} {timing} ON public.{table} FOR EACH {each} EXECUTE FUNCTION public.{fn}({literal})"
        )

    for table in TABLES:
        trig(table, f"{table}_05_no_update", "BEFORE UPDATE", "forbid_update")
        trig(
            table,
            f"{table}_25_member",
            "BEFORE INSERT",
            "assert_active_member",
            "created_by_user_id",
        )
        trig(table, f"{table}_no_delete", "BEFORE DELETE", "forbid_delete")
        trig(table, f"{table}_no_truncate", "BEFORE TRUNCATE", "forbid_truncate", each="STATEMENT")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({SCOPE})")
        op.execute(
            f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({_write_check(table)})"
        )
        op.execute(f"GRANT SELECT ON {table} TO apm_app")
    trig(
        ENTITIES, f"{ENTITIES}_95_audit", "AFTER INSERT OR UPDATE", "audit_row_change",
        "id,organization_id,school_id,state", "legal_name,cnpj,address,city", "id", "",
    )  # fmt: skip
    trig(
        CARRYOVERS, f"{CARRYOVERS}_95_audit", "AFTER INSERT OR UPDATE", "audit_row_change",
        "id,organization_id,school_id,year,program,custeio_cents,capital_cents", "program_label", "id", "",
    )  # fmt: skip
    op.execute(
        f"GRANT INSERT (organization_id, school_id, legal_name, cnpj, address, city, state, created_by_user_id) ON {ENTITIES} TO apm_app"
    )
    op.execute(
        f"GRANT INSERT (organization_id, school_id, year, program, program_label, custeio_cents, "
        f"capital_cents, created_by_user_id) ON {CARRYOVERS} TO apm_app"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for table in (CARRYOVERS, ENTITIES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    # Lines already classified as a yield or a return cannot go back to the old list of kinds (nothing is
    # deleted): the downgrade stops there, and the backup of the day is the way back.
    op.execute("DROP TRIGGER pdde_classifications_95_audit ON public.pdde_classifications")
    op.execute(CLASSIFICATION_AUDIT_OLD)
    op.execute(CLASSIFICATION_CHECK_OLD)
    op.execute("ALTER TABLE pdde_classifications DROP CONSTRAINT ck_pdde_classifications_shape")
    op.execute(
        f"ALTER TABLE pdde_classifications ADD CONSTRAINT ck_pdde_classifications_shape CHECK ({SHAPE_OLD})"
    )
    op.execute(
        "ALTER TABLE pdde_classifications DROP CONSTRAINT ck_pdde_classifications_kind_valid"
    )
    op.execute(
        f"ALTER TABLE pdde_classifications ADD CONSTRAINT ck_pdde_classifications_kind_valid CHECK (kind IN ({KINDS_OLD}))"
    )
    op.execute(
        "ALTER TABLE pdde_classifications DROP CONSTRAINT ck_pdde_classifications_payment_number_length"
    )
    op.execute("ALTER TABLE pdde_classifications DROP COLUMN payment_number")
    op.execute("DROP TRIGGER pdde_documents_05_immutable ON public.pdde_documents")
    op.execute("DROP TRIGGER pdde_documents_95_audit ON public.pdde_documents")
    for column in ("specification", "quantity", "vendor_tax_id"):
        op.execute(f"ALTER TABLE pdde_documents DROP COLUMN {column}")
    for statement in _document_triggers((), "access_key,doc_number,vendor"):
        op.execute(statement)
    op.execute("RESET ROLE")
