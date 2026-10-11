"""staff requests: a collaborator asks the management for something, with photos

Revision ID: 0012_staff_requests
Revises: 0011_employee_wording
Create Date: 2026-10-11

A `funcionário` opens a request (a category, a title, a description, photos); the management sees
the inbox, marks it IN_PROGRESS and RESOLVED (with a note the author reads). It is not money, so it
is outside the ledger, but it follows the rules of every tenant table (docs/tenancy.md, "How to
create a new tenant table", and docs/financial-model.md for the traps of the TASK-005 review):

* both tables carry the organization and the school, with the composite foreign keys, and every
  unique index carries `school_id`;
* `*_user_id` columns are foreign keys to the global `users`, guarded by `assert_active_member`
  (a uniform error, so neither an existing nor an unknown user is an oracle);
* the write policies also require that the school belongs to the organization of the row;
* the application role writes by column and can never DELETE; the triggers freeze what must not
  change and the final states;
* the audit trigger never copies free text (title, description, note, file names).

The categories are a fixed set (a CHECK) for now: custom categories are a later decision.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_staff_requests"
down_revision: str | None = "0011_employee_wording"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEX64 = "^[0-9a-f]{64}$"
HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"
TABLES = ("staff_requests", "staff_request_attachments")
CATEGORIES = "'SUPPLIES', 'MAINTENANCE', 'EVENT', 'FINANCE', 'OTHER'"
STATUSES = "'OPEN', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED'"
IMAGE_TYPES = "'image/png', 'image/jpeg', 'image/webp'"

# The same scope predicate of the other tenant tables (0004, 0007).
SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)


def _write_check(table: str) -> str:
    in_school = (
        "EXISTS (SELECT 1 FROM public.schools s "
        f"WHERE s.id = {table}.school_id AND s.organization_id = {table}.organization_id)"
    )
    return f"({SCOPE} AND {in_school})"


FUNCTIONS = {
    "staff_requests_check_change": f"""
CREATE FUNCTION public.staff_requests_check_change() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'OPEN' AND NEW.status IN ('IN_PROGRESS', 'RESOLVED', 'CANCELLED'))
        OR (OLD.status = 'IN_PROGRESS' AND NEW.status IN ('RESOLVED', 'CANCELLED'))
    ) THEN
        RAISE EXCEPTION 'a staff request cannot go from % to %', OLD.status, NEW.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
    "staff_request_attachments_check_state": f"""
CREATE FUNCTION public.staff_request_attachments_check_state() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.staff_requests r
        WHERE r.id = NEW.request_id AND r.organization_id = NEW.organization_id
          AND r.school_id = NEW.school_id AND r.status IN ('OPEN', 'IN_PROGRESS')
    ) THEN
        RAISE EXCEPTION 'files can only be attached to an open staff request'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$body$
""",
}


def _literal(values: Sequence[str]) -> str:
    return ", ".join("'" + value + "'" for value in values)


def _trigger(
    table: str, name: str, timing: str, function: str, *args: str, statement: bool = False
) -> str:
    each = "FOR EACH STATEMENT" if statement else "FOR EACH ROW"
    return (
        f"CREATE TRIGGER {name} {timing} ON public.{table} {each} "
        f"EXECUTE FUNCTION public.{function}({_literal(args)})"
    )


def _create_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE staff_requests (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            author_user_id uuid NOT NULL,
            category text NOT NULL,
            title text NOT NULL,
            description text,
            status text NOT NULL DEFAULT 'OPEN',
            started_at timestamptz,
            started_by_user_id uuid,
            resolved_at timestamptz,
            resolved_by_user_id uuid,
            resolution_note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_staff_requests PRIMARY KEY (id),
            CONSTRAINT fk_staff_requests_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_requests_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_requests_author_user_id_users
                FOREIGN KEY (author_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_requests_started_by_user_id_users
                FOREIGN KEY (started_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_requests_resolved_by_user_id_users
                FOREIGN KEY (resolved_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            -- Target of the composite foreign key of the attachments.
            CONSTRAINT uq_staff_requests_id_organization_id_school_id
                UNIQUE (id, organization_id, school_id),
            CONSTRAINT ck_staff_requests_category_valid CHECK (category IN ({CATEGORIES})),
            CONSTRAINT ck_staff_requests_status_valid CHECK (status IN ({STATUSES})),
            CONSTRAINT ck_staff_requests_title_length
                CHECK (length(btrim(title)) BETWEEN 1 AND 120),
            CONSTRAINT ck_staff_requests_description_length
                CHECK (description IS NULL OR length(description) <= 2000),
            CONSTRAINT ck_staff_requests_resolution_note_length
                CHECK (resolution_note IS NULL OR length(btrim(resolution_note)) BETWEEN 1 AND 1000),
            CONSTRAINT ck_staff_requests_started_has_a_person
                CHECK ((started_at IS NULL) = (started_by_user_id IS NULL)),
            CONSTRAINT ck_staff_requests_resolved_has_a_person
                CHECK ((resolved_at IS NULL) = (resolved_by_user_id IS NULL)),
            CONSTRAINT ck_staff_requests_resolved_iff_status
                CHECK ((status = 'RESOLVED') = (resolved_at IS NOT NULL)),
            CONSTRAINT ck_staff_requests_note_only_when_resolved
                CHECK (resolution_note IS NULL OR status = 'RESOLVED')
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_staff_requests_school_id_created_at "
        "ON staff_requests (school_id, created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_staff_requests_school_id_status ON staff_requests (school_id, status)"
    )
    op.execute(
        "CREATE INDEX ix_staff_requests_school_id_author_user_id "
        "ON staff_requests (school_id, author_user_id)"
    )
    op.execute(
        f"""
        CREATE TABLE staff_request_attachments (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            school_id uuid NOT NULL,
            request_id uuid NOT NULL,
            storage_key text NOT NULL,
            file_name text NOT NULL,
            content_type text NOT NULL,
            size_bytes bigint NOT NULL,
            sha256 text NOT NULL,
            uploaded_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_staff_request_attachments PRIMARY KEY (id),
            CONSTRAINT fk_staff_request_attachments_organization_id_organizations
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_request_attachments_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id)
                REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_request_attachments_request_id_staff_requests
                FOREIGN KEY (request_id, organization_id, school_id)
                REFERENCES staff_requests (id, organization_id, school_id) ON DELETE RESTRICT,
            CONSTRAINT fk_staff_request_attachments_uploaded_by_user_id_users
                FOREIGN KEY (uploaded_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_staff_request_attachments_school_id_request_id_sha256
                UNIQUE (school_id, request_id, sha256),
            CONSTRAINT ck_staff_request_attachments_storage_key_length
                CHECK (length(storage_key) BETWEEN 1 AND 500 AND storage_key !~ '^/'),
            CONSTRAINT ck_staff_request_attachments_file_name_length
                CHECK (length(btrim(file_name)) BETWEEN 1 AND 255),
            CONSTRAINT ck_staff_request_attachments_content_type_image
                CHECK (content_type IN ({IMAGE_TYPES})),
            CONSTRAINT ck_staff_request_attachments_size_range
                CHECK (size_bytes BETWEEN 1 AND 20971520),
            CONSTRAINT ck_staff_request_attachments_sha256_format CHECK (sha256 ~ '{HEX64}')
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_staff_request_attachments_request_id "
        "ON staff_request_attachments (request_id)"
    )
    op.execute(
        "CREATE INDEX ix_staff_request_attachments_school_id ON staff_request_attachments (school_id)"
    )


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
            "staff_requests",
            "staff_requests_05_immutable",
            "BEFORE UPDATE",
            "assert_immutable_columns",
            "id",
            "organization_id",
            "school_id",
            "author_user_id",
            "category",
            "title",
            "description",
            "created_at",
        ),
        _trigger(
            "staff_requests",
            "staff_requests_06_freeze",
            "BEFORE UPDATE",
            "freeze_when_final",
            "RESOLVED",
            "CANCELLED",
        ),
        _trigger(
            "staff_requests",
            "staff_requests_07_change",
            "BEFORE UPDATE",
            "staff_requests_check_change",
        ),
        _trigger(
            "staff_requests",
            "staff_requests_10_set_once",
            "BEFORE UPDATE",
            "assert_set_once_columns",
            "started_at",
            "started_by_user_id",
            "resolved_at",
            "resolved_by_user_id",
            "resolution_note",
        ),
        _trigger(
            "staff_requests",
            "staff_requests_25_member",
            "BEFORE INSERT OR UPDATE OF author_user_id, started_by_user_id, resolved_by_user_id",
            "assert_active_member",
            "author_user_id",
            "started_by_user_id",
            "resolved_by_user_id",
        ),
        _trigger(
            "staff_requests",
            "staff_requests_95_audit",
            "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,author_user_id,category,status,started_at,"
            "started_by_user_id,resolved_at,resolved_by_user_id",
            "title,description,resolution_note",
            "id",
            "",
        ),
        _trigger(
            "staff_request_attachments",
            "staff_request_attachments_05_no_update",
            "BEFORE UPDATE",
            "forbid_update",
        ),
        _trigger(
            "staff_request_attachments",
            "staff_request_attachments_20_state",
            "BEFORE INSERT",
            "staff_request_attachments_check_state",
        ),
        _trigger(
            "staff_request_attachments",
            "staff_request_attachments_25_member",
            "BEFORE INSERT",
            "assert_active_member",
            "uploaded_by_user_id",
        ),
        _trigger(
            "staff_request_attachments",
            "staff_request_attachments_95_audit",
            "AFTER INSERT OR UPDATE",
            "audit_row_change",
            "id,organization_id,school_id,request_id,content_type,size_bytes,sha256,"
            "uploaded_by_user_id",
            "file_name,storage_key",
            "id",
            "",
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


def _enable_rls_and_grant() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({SCOPE})")
        op.execute(
            f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({_write_check(table)})"
        )
    op.execute(
        "CREATE POLICY staff_requests_update ON staff_requests FOR UPDATE "
        f"USING ({SCOPE}) WITH CHECK ({_write_check('staff_requests')})"
    )
    # No DELETE policy and no DELETE grant: a request is never removed. The id, the status and the
    # timestamps of a new row are the database's (the defaults), not the caller's.
    op.execute("GRANT SELECT ON staff_requests, staff_request_attachments TO apm_app")
    op.execute(
        "GRANT INSERT (organization_id, school_id, author_user_id, category, title, description) "
        "ON staff_requests TO apm_app"
    )
    op.execute(
        "GRANT UPDATE (status, started_at, started_by_user_id, resolved_at, resolved_by_user_id, "
        "resolution_note, updated_at) ON staff_requests TO apm_app"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, request_id, storage_key, file_name, "
        "content_type, size_bytes, sha256, uploaded_by_user_id) "
        "ON staff_request_attachments TO apm_app"
    )


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    _create_tables()
    _create_triggers()
    _enable_rls_and_grant()
    op.execute("RESET ROLE")


def downgrade() -> None:
    # Everything this revision created goes, the requests and their photo rows included (the files
    # on the volume stay: they are not in the database).
    op.execute("SET LOCAL ROLE apm_owner")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{name}()")
    op.execute("RESET ROLE")
