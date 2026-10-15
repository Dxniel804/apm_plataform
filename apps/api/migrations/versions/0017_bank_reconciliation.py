"""bank accounts of a school and the bank statements imported to be compared with the ledger

Revision ID: 0017_bank_reconciliation
Revises: 0016_contribution_fees
Create Date: 2026-10-14

* `bank_accounts`: the accounts where a school receives money (a nickname, the bank, the LAST FOUR
  digits and what it is for: the general fund or the PDDE). A school may have several. The full
  number of an account is never stored.
* `bank_statement_imports`: one file imported (its sha256 stops the same file twice), who sent it and
  the period it covers. The file itself is NOT kept: only the lines.
* `bank_statement_lines`: what the bank says happened (date, signed amount, a short text with the
  CPF and the CNPJ masked, the id the bank gave it and, when the text carries it, the end-to-end id of
  the Pix). Insert-only; a line the bank already sent in an earlier file is not stored twice.

The comparison with the ledger is computed when it is read (a pure function), so nothing here can
disagree with the ledger.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_bank_reconciliation"
down_revision: str | None = "0016_contribution_fees"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)


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
    op.execute(
        f"""
        CREATE TABLE bank_accounts (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            nickname text NOT NULL,
            bank_name text NOT NULL,
            account_last4 text,
            purpose text NOT NULL DEFAULT 'GENERAL',
            is_active boolean NOT NULL DEFAULT true,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_bank_accounts PRIMARY KEY (id),
            {_tenant_fks("bank_accounts")},
            CONSTRAINT fk_bank_accounts_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_bank_accounts_id_organization_id_school_id
                UNIQUE (id, organization_id, school_id),
            CONSTRAINT uq_bank_accounts_school_id_nickname UNIQUE (school_id, nickname),
            CONSTRAINT ck_bank_accounts_nickname_length CHECK (length(btrim(nickname)) BETWEEN 1 AND 60),
            CONSTRAINT ck_bank_accounts_bank_name_length CHECK (length(btrim(bank_name)) BETWEEN 1 AND 60),
            CONSTRAINT ck_bank_accounts_last4_format
                CHECK (account_last4 IS NULL OR account_last4 ~ '^[0-9]{{1,4}}$'),
            CONSTRAINT ck_bank_accounts_purpose_valid CHECK (purpose IN ('GENERAL', 'PDDE'))
        )
        """
    )
    op.execute("CREATE INDEX ix_bank_accounts_school_id ON bank_accounts (school_id)")
    op.execute(
        f"""
        CREATE TABLE bank_statement_imports (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            bank_account_id uuid NOT NULL,
            file_sha256 text NOT NULL,
            period_start date NOT NULL,
            period_end date NOT NULL,
            line_count integer NOT NULL,
            new_line_count integer NOT NULL,
            closing_balance_cents bigint,
            uploaded_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_bank_statement_imports PRIMARY KEY (id),
            {_tenant_fks("bank_statement_imports")},
            CONSTRAINT fk_bank_statement_imports_bank_account_id_bank_accounts
                FOREIGN KEY (bank_account_id, organization_id, school_id)
                REFERENCES bank_accounts (id, organization_id, school_id) ON DELETE RESTRICT,
            CONSTRAINT fk_bank_statement_imports_uploaded_by_user_id_users
                FOREIGN KEY (uploaded_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_bank_statement_imports_id_organization_id_school_id
                UNIQUE (id, organization_id, school_id),
            -- The same file twice is refused, per school (never global: a clash would answer for others).
            CONSTRAINT uq_bank_statement_imports_school_id_file_sha256 UNIQUE (school_id, file_sha256),
            CONSTRAINT ck_bank_statement_imports_sha256_format CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT ck_bank_statement_imports_period_in_order CHECK (period_start <= period_end),
            CONSTRAINT ck_bank_statement_imports_line_counts
                CHECK (line_count BETWEEN 1 AND 5000 AND new_line_count BETWEEN 0 AND line_count)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_bank_statement_imports_school_id ON bank_statement_imports (school_id, created_at DESC)"
    )
    op.execute(
        f"""
        CREATE TABLE bank_statement_lines (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            import_id uuid NOT NULL,
            bank_account_id uuid NOT NULL,
            posted_on date NOT NULL,
            amount_cents bigint NOT NULL,
            memo text NOT NULL,
            bank_ref text NOT NULL,
            end_to_end_id text,
            looks_like_fee boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_bank_statement_lines PRIMARY KEY (id),
            {_tenant_fks("bank_statement_lines")},
            CONSTRAINT fk_bank_statement_lines_import_id_bank_statement_imports
                FOREIGN KEY (import_id, organization_id, school_id)
                REFERENCES bank_statement_imports (id, organization_id, school_id) ON DELETE RESTRICT,
            CONSTRAINT fk_bank_statement_lines_bank_account_id_bank_accounts
                FOREIGN KEY (bank_account_id, organization_id, school_id)
                REFERENCES bank_accounts (id, organization_id, school_id) ON DELETE RESTRICT,
            -- A line the bank already sent in an earlier file is the same line.
            CONSTRAINT uq_bank_statement_lines_school_id_bank_account_id_bank_ref
                UNIQUE (school_id, bank_account_id, bank_ref),
            CONSTRAINT ck_bank_statement_lines_amount_range
                CHECK (amount_cents <> 0 AND abs(amount_cents) <= 100000000000),
            CONSTRAINT ck_bank_statement_lines_memo_length CHECK (length(memo) <= 200),
            CONSTRAINT ck_bank_statement_lines_bank_ref_length CHECK (length(bank_ref) BETWEEN 1 AND 255),
            CONSTRAINT ck_bank_statement_lines_e2e_format
                CHECK (end_to_end_id IS NULL OR end_to_end_id ~ '^E[0-9A-Za-z]{{31}}$')
        )
        """
    )
    op.execute("CREATE INDEX ix_bank_statement_lines_import_id ON bank_statement_lines (import_id)")
    op.execute(
        "CREATE INDEX ix_bank_statement_lines_school_id_posted_on ON bank_statement_lines (school_id, posted_on)"
    )

    def trig(table: str, name: str, timing: str, fn: str, *args: str, each: str = "ROW") -> None:
        literal = ", ".join("'" + a + "'" for a in args)
        op.execute(
            f"CREATE TRIGGER {name} {timing} ON public.{table} FOR EACH {each} EXECUTE FUNCTION public.{fn}({literal})"
        )

    trig("bank_accounts", "bank_accounts_05_immutable", "BEFORE UPDATE", "assert_immutable_columns",
         "id", "organization_id", "school_id", "created_by_user_id", "created_at")  # fmt: skip
    trig(
        "bank_accounts",
        "bank_accounts_25_member",
        "BEFORE INSERT",
        "assert_active_member",
        "created_by_user_id",
    )
    trig("bank_accounts", "bank_accounts_95_audit", "AFTER INSERT OR UPDATE", "audit_row_change",
         "id,organization_id,school_id,account_last4,purpose,is_active", "nickname,bank_name", "id", "")  # fmt: skip
    trig(
        "bank_statement_imports",
        "bank_statement_imports_05_no_update",
        "BEFORE UPDATE",
        "forbid_update",
    )
    trig(
        "bank_statement_imports",
        "bank_statement_imports_25_member",
        "BEFORE INSERT",
        "assert_active_member",
        "uploaded_by_user_id",
    )
    trig("bank_statement_imports", "bank_statement_imports_95_audit", "AFTER INSERT OR UPDATE", "audit_row_change",
         "id,organization_id,school_id,bank_account_id,period_start,period_end,line_count,new_line_count,file_sha256", "", "id", "")  # fmt: skip
    trig(
        "bank_statement_lines",
        "bank_statement_lines_05_no_update",
        "BEFORE UPDATE",
        "forbid_update",
    )
    for table in ("bank_accounts", "bank_statement_imports", "bank_statement_lines"):
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
        f"CREATE POLICY bank_accounts_update ON bank_accounts FOR UPDATE USING ({SCOPE}) WITH CHECK ({_write_check('bank_accounts')})"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, nickname, bank_name, account_last4, purpose, created_by_user_id) "
        "ON bank_accounts TO apm_app"
    )
    op.execute(
        "GRANT UPDATE (nickname, bank_name, account_last4, purpose, is_active, updated_at) ON bank_accounts TO apm_app"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, bank_account_id, file_sha256, period_start, period_end, "
        "line_count, new_line_count, closing_balance_cents, uploaded_by_user_id) ON bank_statement_imports TO apm_app"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, import_id, bank_account_id, posted_on, amount_cents, memo, "
        "bank_ref, end_to_end_id, looks_like_fee) ON bank_statement_lines TO apm_app"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TABLE IF EXISTS bank_statement_lines")
    op.execute("DROP TABLE IF EXISTS bank_statement_imports")
    op.execute("DROP TABLE IF EXISTS bank_accounts")
    op.execute("RESET ROLE")
