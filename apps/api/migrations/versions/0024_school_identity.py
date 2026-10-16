# ruff: noqa: E501
"""the school chooses its name and the address of its link (docs/adr-school-identity.md)

Revision ID: 0024_school_identity
Revises: 0023_forklin_sso
Create Date: 2026-10-16

The address of a school (`/escola/<slug>`) is on posters and QR codes and families PAY through it, so:

* **every address a school ever had stays reserved to it** (`school_slug_history`, one global
  namespace: nobody else can ever take it) and keeps opening the school: `resolve_school_public`
  also finds a school by an old address, and the site redirects to the current one;
* the **name** changes freely (the column was already grantable); the **address** changes twice
  freely, and from the third change only 15 days after the previous one. That rule lives in a trigger,
  so no code of the application can skip it;
* a few words that the site itself uses are reserved (`admin`, `api`, `login`...) and an address has
  at least 3 characters.

New SQLSTATEs the API maps to answers: AP001 reserved word, AP002 change locked (15 days), AP003 too short.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_school_identity"
down_revision: str | None = "0023_forklin_sso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADER = "LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog"

RESERVED = (
    "admin", "api", "app", "apm", "www", "login", "logout", "painel", "escola", "sso", "convite",
    "accept-invitation", "esqueci-senha", "redefinir-senha", "public", "static", "health", "demo",
    "forklin", "suporte", "ajuda", "termos", "privacidade", "contato", "sistema", "teste",
)  # fmt: skip
RESERVED_SQL = ", ".join(f"'{word}'" for word in RESERVED)

RECORD = f"""
CREATE FUNCTION public.schools_record_slug() RETURNS trigger {HEADER} AS $body$
BEGIN
    -- The first address of a school enters the history; an address somebody already had is refused
    -- (unique_violation), whoever tries to create a school with it.
    INSERT INTO public.school_slug_history (slug, school_id, organization_id)
    VALUES (NEW.slug, NEW.id, NEW.organization_id);
    RETURN NEW;
END
$body$
"""

GUARD = f"""
CREATE FUNCTION public.schools_guard_identity() RETURNS trigger {HEADER} AS $body$
BEGIN
    IF NEW.slug IS DISTINCT FROM OLD.slug THEN
        IF length(NEW.slug) < 3 THEN
            RAISE EXCEPTION 'the address is too short' USING ERRCODE = 'AP003';
        END IF;
        IF NEW.slug = ANY (ARRAY[{RESERVED_SQL}]) THEN
            RAISE EXCEPTION 'the address is reserved' USING ERRCODE = 'AP001';
        END IF;
        -- Two free changes; from the third, 15 days after the previous one.
        IF OLD.slug_changes >= 2 AND OLD.slug_changed_at IS NOT NULL
           AND OLD.slug_changed_at > now() - interval '15 days' THEN
            RAISE EXCEPTION 'the address was changed too recently' USING ERRCODE = 'AP002';
        END IF;
        -- Every address ever used stays in the history. An address of ANOTHER school (current or old) is
        -- a unique_violation; going back to an address this school itself had is allowed (the history
        -- is tenant-scoped, so what this school can see there is its own).
        IF NOT EXISTS (
            SELECT 1 FROM public.school_slug_history h WHERE h.slug = NEW.slug AND h.school_id = OLD.id
        ) THEN
            INSERT INTO public.school_slug_history (slug, school_id, organization_id)
            VALUES (NEW.slug, OLD.id, OLD.organization_id);
        END IF;
        NEW.slug_changes := OLD.slug_changes + 1;
        NEW.slug_changed_at := now();
        INSERT INTO public.audit_logs
            (organization_id, school_id, action, entity_type, entity_id, before_data, after_data)
        VALUES (OLD.organization_id, OLD.id, 'schools.slug_changed', 'schools', OLD.id,
                jsonb_build_object('slug', OLD.slug), jsonb_build_object('slug', NEW.slug));
    ELSE
        -- The counters are the trigger's: whatever the statement says, they do not move.
        NEW.slug_changes := OLD.slug_changes;
        NEW.slug_changed_at := OLD.slug_changed_at;
    END IF;
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        INSERT INTO public.audit_logs
            (organization_id, school_id, action, entity_type, entity_id, before_data, after_data)
        VALUES (OLD.organization_id, OLD.id, 'schools.renamed', 'schools', OLD.id,
                jsonb_build_object('name', OLD.name), jsonb_build_object('name', NEW.name));
    END IF;
    RETURN NEW;
END
$body$
"""

RESOLVE_WITH_HISTORY = """
CREATE OR REPLACE FUNCTION public.resolve_school_public(p_slug text)
RETURNS TABLE (
    organization_id uuid, school_id uuid, slug text, name text, accent_color text,
    accent_contrast_color text, suggested_amounts_cents bigint[], allow_custom_amount boolean,
    min_amount_cents bigint, max_amount_cents bigint, required_fields text[], optional_fields text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
    SELECT s.organization_id, s.id, s.slug, s.name, c.brand_accent, c.brand_accent_contrast,
           c.suggested_amounts_cents, c.allow_custom_amount, c.min_contribution_cents,
           c.max_contribution_cents, c.required_fields, c.optional_fields
    FROM public.schools s
    JOIN public.school_settings c ON c.school_id = s.id
    WHERE s.slug = p_slug
       OR s.id = (SELECT h.school_id FROM public.school_slug_history h WHERE h.slug = p_slug)
    LIMIT 1
$fn$
"""

RESOLVE_ORIGINAL = """
CREATE OR REPLACE FUNCTION public.resolve_school_public(p_slug text)
RETURNS TABLE (
    organization_id uuid, school_id uuid, slug text, name text, accent_color text,
    accent_contrast_color text, suggested_amounts_cents bigint[], allow_custom_amount boolean,
    min_amount_cents bigint, max_amount_cents bigint, required_fields text[], optional_fields text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
    SELECT s.organization_id, s.id, s.slug, s.name, c.brand_accent, c.brand_accent_contrast,
           c.suggested_amounts_cents, c.allow_custom_amount, c.min_contribution_cents,
           c.max_contribution_cents, c.required_fields, c.optional_fields
    FROM public.schools s
    JOIN public.school_settings c ON c.school_id = s.id
    WHERE s.slug = p_slug
    LIMIT 1
$fn$
"""

SCOPE = (
    "(organization_id = (SELECT public.app_org()) AND "
    "((SELECT public.app_school()) IS NULL OR school_id = (SELECT public.app_school())))"
)
ACTIVE_ACCOUNT = (
    "EXISTS (SELECT 1 FROM public.payment_accounts a "
    "WHERE a.school_id = school_slug_history.school_id AND a.status = 'ACTIVE')"
)
FROM_THE_CENTRAL = (
    "EXISTS (SELECT 1 FROM public.organizations o "
    "WHERE o.id = school_slug_history.organization_id AND o.central_org_id IS NOT NULL)"
)


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE schools ADD COLUMN slug_changes integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE schools ADD COLUMN slug_changed_at timestamptz")
    op.execute(
        "ALTER TABLE schools ADD CONSTRAINT ck_schools_slug_changes_not_negative CHECK (slug_changes >= 0)"
    )
    op.execute(
        """
        CREATE TABLE school_slug_history (
            slug text NOT NULL,
            school_id uuid NOT NULL,
            organization_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_school_slug_history PRIMARY KEY (slug),
            CONSTRAINT fk_school_slug_history_school_id_organization_id_schools
                FOREIGN KEY (school_id, organization_id) REFERENCES schools (id, organization_id) ON DELETE RESTRICT,
            CONSTRAINT ck_school_slug_history_slug_format CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
        )
        """
    )
    op.execute("CREATE INDEX ix_school_slug_history_school_id ON school_slug_history (school_id)")
    op.execute("ALTER TABLE school_slug_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE school_slug_history FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY school_slug_history_select ON school_slug_history FOR SELECT USING {SCOPE}"
    )
    op.execute(
        f"CREATE POLICY school_slug_history_insert ON school_slug_history FOR INSERT WITH CHECK {SCOPE}"
    )

    # The addresses the schools already have go into the history (the owner reads schools only with
    # row level security off for this one statement).
    op.execute("ALTER TABLE schools NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE school_slug_history NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO school_slug_history (slug, school_id, organization_id) "
        "SELECT slug, id, organization_id FROM schools"
    )
    op.execute("ALTER TABLE school_slug_history FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schools FORCE ROW LEVEL SECURITY")

    op.execute(RECORD)
    op.execute(GUARD)
    op.execute(
        """
        DO $$
        DECLARE
            f record;
        BEGIN
            FOR f IN
                SELECT p.oid::regprocedure AS signature FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.proname IN ('schools_record_slug', 'schools_guard_identity')
            LOOP
                EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', f.signature);
            END LOOP;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER schools_20_identity BEFORE UPDATE ON public.schools "
        "FOR EACH ROW EXECUTE FUNCTION public.schools_guard_identity()"
    )
    op.execute(
        "CREATE TRIGGER schools_15_record_slug AFTER INSERT ON public.schools "
        "FOR EACH ROW EXECUTE FUNCTION public.schools_record_slug()"
    )
    op.execute(
        "CREATE TRIGGER school_slug_history_no_update BEFORE UPDATE ON public.school_slug_history "
        "FOR EACH ROW EXECUTE FUNCTION public.forbid_update()"
    )
    op.execute(
        "CREATE TRIGGER school_slug_history_no_delete BEFORE DELETE ON public.school_slug_history "
        "FOR EACH ROW EXECUTE FUNCTION public.forbid_delete()"
    )
    op.execute(
        "CREATE TRIGGER school_slug_history_no_truncate BEFORE TRUNCATE ON public.school_slug_history FOR EACH STATEMENT EXECUTE FUNCTION public.forbid_truncate()"
    )

    # --- the application: change the address (the trigger decides if it may) and read the history
    op.execute("GRANT UPDATE (slug) ON schools TO apm_app")
    op.execute("GRANT SELECT, INSERT ON school_slug_history TO apm_app")

    # --- the definer: find a school by an address it had, and record the first address of a school it creates
    op.execute("GRANT SELECT (slug, school_id) ON school_slug_history TO apm_definer")
    op.execute(
        f"CREATE POLICY school_slug_history_definer_select ON school_slug_history FOR SELECT TO apm_definer USING ({ACTIVE_ACCOUNT})"
    )
    op.execute(
        "GRANT INSERT (slug, school_id, organization_id) ON school_slug_history TO apm_definer"
    )
    op.execute(
        f"CREATE POLICY school_slug_history_definer_insert ON school_slug_history FOR INSERT TO apm_definer WITH CHECK ({FROM_THE_CENTRAL})"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(RESOLVE_WITH_HISTORY)
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")


def downgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(RESOLVE_ORIGINAL)
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TRIGGER IF EXISTS schools_20_identity ON public.schools")
    op.execute("DROP TRIGGER IF EXISTS schools_15_record_slug ON public.schools")
    op.execute("REVOKE UPDATE (slug) ON schools FROM apm_app")
    op.execute("DROP TABLE IF EXISTS school_slug_history")
    op.execute("DROP FUNCTION IF EXISTS public.schools_guard_identity()")
    op.execute("DROP FUNCTION IF EXISTS public.schools_record_slug()")
    op.execute("ALTER TABLE schools DROP CONSTRAINT IF EXISTS ck_schools_slug_changes_not_negative")
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS slug_changed_at")
    op.execute("ALTER TABLE schools DROP COLUMN IF EXISTS slug_changes")
    op.execute("RESET ROLE")
