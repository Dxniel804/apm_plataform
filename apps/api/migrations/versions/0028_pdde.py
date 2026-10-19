"""PDDE: the accountability of the federal money, a layer over the lines of the PDDE bank account

Revision ID: 0028_pdde
Revises: 0027_balancete
Create Date: 2026-10-19

The PDDE money (the Básico, the Equidade, the Qualidade, the Conectado) reaches the school in a
bank account of its own, and the school proves how it was spent by CLASSIFYING every line of that
account's statement (the program, custeio or capital, the object) and registering the document of
the expense (Res. CD/FNDE 15/2021, art. 29 to 33; 8/2026, art. 13). The ledger is not touched: this is a
layer over `bank_statement_lines`, and only lines of an account whose purpose is `PDDE` can be
classified.

* `pdde_classifications`: what the management decided about a line. Insert-only; a correction is a
  new row and the latest one counts, so the audit trail keeps who said what. `TRANSFER` is money
  in (a repasse), `EXPENSE` is money out with its program, custeio or capital and object, and three
  special items the bank's screen also has: taxes paid straight to the prefeitura (`TAX_TO_EEX`),
  a refund (`REFUND`) and an expense that is not eligible (`INELIGIBLE`).
* `pdde_documents`: the proof of an expense line (a NF-e by its 44-digit key, or another document).
  The documents of a line never add up to more than the line (one function, under a lock). A
  mistaken document is VOIDED (`voided_at`), never deleted; nothing else about it changes.

Written by who manages the reconciliation (`reconciliation:manage`); the statement lines themselves
are still the bank's word and never change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_pdde"
down_revision: str | None = "0027_balancete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
TABLES = ("pdde_classifications", "pdde_documents")

FUNCTIONS = {
    "pdde_classifications_check": f"""
CREATE FUNCTION public.pdde_classifications_check() RETURNS trigger {HEADER} AS $body$
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
    IF NEW.kind = 'TRANSFER' AND v_amount <= 0 THEN
        RAISE EXCEPTION 'a transfer is money in' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind = 'EXPENSE' AND v_amount >= 0 THEN
        RAISE EXCEPTION 'an expense is money out' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
    "pdde_documents_check": f"""
CREATE FUNCTION public.pdde_documents_check() RETURNS trigger {HEADER} AS $body$
DECLARE
    v_amount bigint;
    v_purpose text;
    v_used bigint;
BEGIN
    SELECT l.amount_cents, a.purpose INTO v_amount, v_purpose
    FROM public.bank_statement_lines l
    JOIN public.bank_accounts a ON a.id = l.bank_account_id
    WHERE l.id = NEW.line_id AND l.school_id = NEW.school_id
      AND l.organization_id = NEW.organization_id;
    IF NOT FOUND OR v_purpose <> 'PDDE' THEN
        RAISE EXCEPTION 'a document belongs to a line of a PDDE account'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_amount >= 0 THEN
        RAISE EXCEPTION 'a document proves an expense, which is money out'
            USING ERRCODE = 'check_violation';
    END IF;
    -- Two people adding documents to the same line at once are put in order.
    PERFORM pg_advisory_xact_lock(hashtext(NEW.line_id::text));
    SELECT coalesce(sum(d.amount_cents), 0)::bigint INTO v_used
    FROM public.pdde_documents d
    WHERE d.line_id = NEW.line_id AND d.voided_at IS NULL;
    IF v_used + NEW.amount_cents > -v_amount THEN
        RAISE EXCEPTION 'the documents of a line cannot be worth more than the line'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
}


def _write_check(table: str) -> str:
    return (
        f"({SCOPE} AND EXISTS (SELECT 1 FROM public.bank_statement_lines l "
        f"WHERE l.id = {table}.line_id AND l.school_id = {table}.school_id "
        f"AND l.organization_id = {table}.organization_id))"
    )


def _tenant_fks(table: str) -> str:
    return (
        f"CONSTRAINT fk_{table}_organization_id_organizations "
        "FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT, "
        f"CONSTRAINT fk_{table}_school_id_organization_id_schools "
        "FOREIGN KEY (school_id, organization_id) REFERENCES schools (id, organization_id) "
        "ON DELETE RESTRICT, "
        f"CONSTRAINT fk_{table}_line_id_bank_statement_lines "
        "FOREIGN KEY (line_id) REFERENCES bank_statement_lines (id) ON DELETE RESTRICT"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for name, function in FUNCTIONS.items():
        op.execute(function)
        # Nobody calls a trigger function by hand: not even PUBLIC (the trigger needs no grant).
        op.execute(f"REVOKE ALL ON FUNCTION public.{name}() FROM PUBLIC")
    op.execute(
        f"""
        CREATE TABLE pdde_classifications (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            line_id uuid NOT NULL,
            kind text NOT NULL,
            program text,
            program_label text,
            economic_category text,
            object text,
            note text,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_pdde_classifications PRIMARY KEY (id),
            {_tenant_fks("pdde_classifications")},
            CONSTRAINT fk_pdde_classifications_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_pdde_classifications_kind_valid
                CHECK (kind IN ('TRANSFER', 'EXPENSE', 'TAX_TO_EEX', 'REFUND', 'INELIGIBLE')),
            CONSTRAINT ck_pdde_classifications_program_valid CHECK (
                program IS NULL OR program IN ('BASICO', 'EQUIDADE', 'QUALIDADE', 'CONECTADO', 'OUTRO')),
            CONSTRAINT ck_pdde_classifications_category_valid
                CHECK (economic_category IS NULL OR economic_category IN ('CUSTEIO', 'CAPITAL')),
            CONSTRAINT ck_pdde_classifications_label_shape CHECK (
                (program IS NOT DISTINCT FROM 'OUTRO') = (program_label IS NOT NULL)
                AND (program_label IS NULL OR length(btrim(program_label)) BETWEEN 1 AND 60)),
            CONSTRAINT ck_pdde_classifications_object_length
                CHECK (object IS NULL OR length(btrim(object)) BETWEEN 1 AND 120),
            CONSTRAINT ck_pdde_classifications_note_length
                CHECK (note IS NULL OR length(note) <= 300),
            -- A repasse has its program and no object; an expense has all three.
            CONSTRAINT ck_pdde_classifications_shape CHECK (
                (kind = 'TRANSFER' AND program IS NOT NULL AND object IS NULL)
                OR (kind = 'EXPENSE' AND program IS NOT NULL AND economic_category IS NOT NULL
                    AND object IS NOT NULL)
                OR kind IN ('TAX_TO_EEX', 'REFUND', 'INELIGIBLE'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pdde_classifications_line_id ON pdde_classifications "
        "(line_id, created_at DESC)"
    )
    op.execute(
        f"""
        CREATE TABLE pdde_documents (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            line_id uuid NOT NULL,
            doc_kind text NOT NULL,
            access_key text,
            doc_number text,
            issued_on date NOT NULL,
            vendor text NOT NULL,
            amount_cents bigint NOT NULL,
            stamped boolean NOT NULL DEFAULT false,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            voided_at timestamptz,
            voided_by_user_id uuid,
            CONSTRAINT pk_pdde_documents PRIMARY KEY (id),
            {_tenant_fks("pdde_documents")},
            CONSTRAINT fk_pdde_documents_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT fk_pdde_documents_voided_by_user_id_users
                FOREIGN KEY (voided_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT ck_pdde_documents_kind_valid
                CHECK (doc_kind IN ('NFE', 'INVOICE', 'RECEIPT', 'OTHER')),
            -- A NF-e is found by its 44-digit access key; another document has no key.
            CONSTRAINT ck_pdde_documents_key_shape CHECK (
                (doc_kind = 'NFE' AND access_key ~ '^[0-9]{{44}}$')
                OR (doc_kind <> 'NFE' AND access_key IS NULL)),
            CONSTRAINT ck_pdde_documents_number_length
                CHECK (doc_number IS NULL OR length(btrim(doc_number)) BETWEEN 1 AND 40),
            CONSTRAINT ck_pdde_documents_vendor_length CHECK (length(btrim(vendor)) BETWEEN 1 AND 120),
            CONSTRAINT ck_pdde_documents_amount_range
                CHECK (amount_cents > 0 AND amount_cents <= 100000000000),
            CONSTRAINT ck_pdde_documents_void_pair
                CHECK ((voided_at IS NULL) = (voided_by_user_id IS NULL))
        )
        """
    )
    op.execute("CREATE INDEX ix_pdde_documents_line_id ON pdde_documents (line_id)")
    # The same NF-e is never the proof of two lines (a voided one may be registered again).
    op.execute(
        "CREATE UNIQUE INDEX uq_pdde_documents_school_id_access_key ON pdde_documents "
        "(school_id, access_key) WHERE access_key IS NOT NULL AND voided_at IS NULL"
    )

    def trig(table: str, name: str, timing: str, fn: str, *args: str, each: str = "ROW") -> None:
        literal = ", ".join("'" + a + "'" for a in args)
        op.execute(
            f"CREATE TRIGGER {name} {timing} ON public.{table} "
            f"FOR EACH {each} EXECUTE FUNCTION public.{fn}({literal})"
        )

    trig(
        "pdde_classifications",
        "pdde_classifications_05_no_update",
        "BEFORE UPDATE",
        "forbid_update",
    )
    trig(
        "pdde_classifications",
        "pdde_classifications_20_check",
        "BEFORE INSERT",
        "pdde_classifications_check",
    )
    trig(
        "pdde_classifications",
        "pdde_classifications_25_member",
        "BEFORE INSERT",
        "assert_active_member",
        "created_by_user_id",
    )
    trig(
        "pdde_classifications",
        "pdde_classifications_95_audit",
        "AFTER INSERT OR UPDATE",
        "audit_row_change",
        "id,organization_id,school_id,line_id,kind,program,economic_category",
        "program_label,object,note",
        "id",
        "",
    )
    trig(
        "pdde_documents",
        "pdde_documents_05_immutable",
        "BEFORE UPDATE",
        "assert_immutable_columns",
        "id", "organization_id", "school_id", "line_id", "doc_kind", "access_key", "doc_number",
        "issued_on", "vendor", "amount_cents", "stamped", "created_by_user_id", "created_at",
    )  # fmt: skip
    trig("pdde_documents", "pdde_documents_20_check", "BEFORE INSERT", "pdde_documents_check")
    trig(
        "pdde_documents",
        "pdde_documents_25_member",
        "BEFORE INSERT",
        "assert_active_member",
        "created_by_user_id",
    )
    trig(
        "pdde_documents",
        "pdde_documents_95_audit",
        "AFTER INSERT OR UPDATE",
        "audit_row_change",
        "id,organization_id,school_id,line_id,doc_kind,amount_cents,issued_on,stamped,voided_at",
        "access_key,doc_number,vendor",
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
        f"CREATE POLICY pdde_documents_update ON pdde_documents FOR UPDATE USING ({SCOPE}) "
        f"WITH CHECK ({_write_check('pdde_documents')})"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, line_id, kind, program, program_label, "
        "economic_category, object, note, created_by_user_id) ON pdde_classifications TO apm_app"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, line_id, doc_kind, access_key, doc_number, "
        "issued_on, vendor, amount_cents, stamped, created_by_user_id) ON pdde_documents TO apm_app"
    )
    op.execute("GRANT UPDATE (voided_at, voided_by_user_id) ON pdde_documents TO apm_app")
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TABLE IF EXISTS pdde_documents")
    op.execute("DROP TABLE IF EXISTS pdde_classifications")
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{name}()")
    op.execute("RESET ROLE")
