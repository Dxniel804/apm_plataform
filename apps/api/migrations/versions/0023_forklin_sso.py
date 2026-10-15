# ruff: noqa: E501
"""sign-in through the Forklin Central: two columns and two SECURITY DEFINER functions (docs/adr-forklin-sso.md)

Revision ID: 0023_forklin_sso
Revises: 0022_two_roles
Create Date: 2026-10-15

Somebody arriving from the Central has no session and no school context yet, so row level security
shows nothing: like the login, the invitation and the password recovery, this needs narrow functions
of apm_definer. The perimeter grows by TWO columns and TWO functions:

* `users.central_user_id` and `organizations.central_org_id` (both unique, both optional: nothing
  changes for anybody who never comes from the Central).
* `provision_forklin_school(central_org_id, name, slug)` creates the (empty) account of an
  organization of the Central: the organization, its single school, and, through the existing
  triggers, the settings and the default categories. It is idempotent.
* `sso_sign_in(central_user_id, central_org_id, email, full_name, role)` finds, links by e-mail or
  creates the person (no password) and makes sure of their membership in that school.

Everything the definer may write is tied to an organization that came from the Central: an insert of
an organization needs a `central_org_id`, and the school, its settings, its categories and the audit
rows must belong to such an organization. The definer role cannot log in, and the application role
can only call the two functions.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_forklin_sso"
down_revision: str | None = "0022_two_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _from_the_central(column: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM public.organizations o "
        f"WHERE o.id = {column} AND o.central_org_id IS NOT NULL)"
    )


PROVISION = """
CREATE FUNCTION public.provision_forklin_school(p_central_org_id uuid, p_name text, p_slug text)
RETURNS TABLE (organization_id uuid, school_id uuid, created boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
#variable_conflict use_column
DECLARE
    org uuid;
    sch uuid;
    candidate text;
    attempt integer := 0;
BEGIN
    IF p_central_org_id IS NULL OR p_name IS NULL OR btrim(p_name) = '' OR p_slug IS NULL THEN
        RETURN;
    END IF;
    SELECT o.id INTO org FROM public.organizations o WHERE o.central_org_id = p_central_org_id;
    IF FOUND THEN
        SELECT s.id INTO sch FROM public.schools s WHERE s.organization_id = org;
        RETURN QUERY SELECT org, sch, false;
        RETURN;
    END IF;
    LOOP
        candidate := CASE WHEN attempt = 0 THEN p_slug
                          ELSE left(p_slug, 70) || '-' || substr(md5(p_central_org_id::text || attempt::text), 1, 4) END;
        BEGIN
            INSERT INTO public.organizations (name, slug, central_org_id)
            VALUES (btrim(p_name), candidate, p_central_org_id)
            RETURNING id INTO org;
            INSERT INTO public.schools (organization_id, name, slug)
            VALUES (org, btrim(p_name), candidate)
            RETURNING id INTO sch;
            RETURN QUERY SELECT org, sch, true;
            RETURN;
        EXCEPTION WHEN unique_violation THEN
            -- Another request created this organization first, or the slug is taken.
            SELECT o.id INTO org FROM public.organizations o WHERE o.central_org_id = p_central_org_id;
            IF FOUND THEN
                SELECT s.id INTO sch FROM public.schools s WHERE s.organization_id = org;
                RETURN QUERY SELECT org, sch, false;
                RETURN;
            END IF;
            attempt := attempt + 1;
            IF attempt > 5 THEN
                RETURN;
            END IF;
        END;
    END LOOP;
END
$fn$
"""

SIGN_IN = """
CREATE FUNCTION public.sso_sign_in(
    p_central_user_id uuid, p_central_org_id uuid, p_email text, p_full_name text, p_role text)
RETURNS TABLE (outcome text, user_id uuid, membership_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
#variable_conflict use_column
DECLARE
    org uuid;
    sch uuid;
    usr record;
    uid uuid;
    mem record;
    mid uuid;
BEGIN
    IF p_central_user_id IS NULL OR p_central_org_id IS NULL OR p_email IS NULL OR btrim(p_email) = ''
       OR p_full_name IS NULL OR btrim(p_full_name) = '' OR p_role IS NULL
       OR p_role NOT IN ('secretaria', 'staff') THEN
        RETURN QUERY SELECT 'invalid'::text, NULL::uuid, NULL::uuid;
        RETURN;
    END IF;
    SELECT o.id, s.id INTO org, sch
      FROM public.organizations o JOIN public.schools s ON s.organization_id = o.id
     WHERE o.central_org_id = p_central_org_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'org_unknown'::text, NULL::uuid, NULL::uuid;
        RETURN;
    END IF;

    SELECT u.id AS id, u.is_active AS is_active INTO usr
      FROM public.users u WHERE u.central_user_id = p_central_user_id;
    IF FOUND THEN
        IF NOT usr.is_active THEN
            RETURN QUERY SELECT 'inactive'::text, NULL::uuid, NULL::uuid;
            RETURN;
        END IF;
        uid := usr.id;
    ELSE
        SELECT u.id AS id, u.is_active AS is_active, u.central_user_id AS central_user_id INTO usr
          FROM public.users u WHERE lower(u.email) = lower(p_email);
        IF FOUND THEN
            -- Never merges: an e-mail already tied to another person of the Central is a conflict.
            IF usr.central_user_id IS NOT NULL THEN
                RETURN QUERY SELECT 'conflict'::text, NULL::uuid, NULL::uuid;
                RETURN;
            END IF;
            IF NOT usr.is_active THEN
                RETURN QUERY SELECT 'inactive'::text, NULL::uuid, NULL::uuid;
                RETURN;
            END IF;
            UPDATE public.users SET central_user_id = p_central_user_id, updated_at = now()
             WHERE id = usr.id;
            uid := usr.id;
        ELSE
            BEGIN
                INSERT INTO public.users (email, full_name, central_user_id)
                VALUES (lower(btrim(p_email)), btrim(p_full_name), p_central_user_id)
                RETURNING id INTO uid;
            EXCEPTION WHEN unique_violation THEN
                RETURN QUERY SELECT 'conflict'::text, NULL::uuid, NULL::uuid;
                RETURN;
            END;
        END IF;
    END IF;

    -- The Central is the source of the role. A membership that is not active stays out (the
    -- secretaria suspended that person here): row level security shows the definer only the active ones.
    SELECT m.id AS id, m.role AS role INTO mem
      FROM public.memberships m WHERE m.user_id = uid AND m.school_id = sch;
    IF FOUND THEN
        IF mem.role <> p_role THEN
            UPDATE public.memberships SET role = p_role, updated_at = now() WHERE id = mem.id;
        END IF;
        mid := mem.id;
    ELSE
        BEGIN
            INSERT INTO public.memberships (user_id, organization_id, school_id, role, status)
            VALUES (uid, org, sch, p_role, 'active')
            RETURNING id INTO mid;
        EXCEPTION WHEN unique_violation THEN
            RETURN QUERY SELECT 'suspended'::text, NULL::uuid, NULL::uuid;
            RETURN;
        END;
    END IF;
    RETURN QUERY SELECT 'ok'::text, uid, mid;
END
$fn$
"""


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("ALTER TABLE users ADD COLUMN central_user_id uuid")
    op.execute("ALTER TABLE organizations ADD COLUMN central_org_id uuid")
    op.execute("CREATE UNIQUE INDEX uq_users_central_user_id ON users (central_user_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_organizations_central_org_id ON organizations (central_org_id)"
    )

    # --- what the definer may read and write, tied to organizations of the Central ------------------
    op.execute("GRANT SELECT (central_user_id) ON users TO apm_definer")
    op.execute("GRANT INSERT (central_user_id) ON users TO apm_definer")
    op.execute("GRANT UPDATE (central_user_id, updated_at) ON users TO apm_definer")
    op.execute("DROP POLICY users_definer_insert ON users")
    op.execute(
        "CREATE POLICY users_definer_insert ON users FOR INSERT TO apm_definer "
        "WITH CHECK (is_active AND (password_hash IS NOT NULL OR central_user_id IS NOT NULL))"
    )
    # Only a person who has no link yet gets one, and only an active one.
    op.execute(
        "CREATE POLICY users_definer_link ON users FOR UPDATE TO apm_definer "
        "USING (is_active AND central_user_id IS NULL) WITH CHECK (is_active AND central_user_id IS NOT NULL)"
    )

    op.execute("GRANT UPDATE (role, updated_at) ON memberships TO apm_definer")
    op.execute(
        # Only the role (a text with a CHECK of two values) and updated_at are granted, and only an
        # active row: it cannot reactivate, move or suspend anybody. (No subquery here: one on
        # organizations would loop back through its policy to this table.)
        "CREATE POLICY memberships_definer_update ON memberships FOR UPDATE TO apm_definer "
        "USING (status = 'active') WITH CHECK (status = 'active')"
    )

    op.execute("GRANT SELECT (central_org_id) ON organizations TO apm_definer")
    op.execute("GRANT INSERT (name, slug, central_org_id) ON organizations TO apm_definer")
    op.execute("DROP POLICY organizations_definer_select ON organizations")
    op.execute(
        "CREATE POLICY organizations_definer_select ON organizations FOR SELECT TO apm_definer "
        "USING (central_org_id IS NOT NULL OR EXISTS "
        "(SELECT 1 FROM public.memberships m WHERE m.organization_id = organizations.id))"
    )
    op.execute(
        "CREATE POLICY organizations_definer_insert ON organizations FOR INSERT TO apm_definer "
        "WITH CHECK (central_org_id IS NOT NULL)"
    )

    op.execute("GRANT INSERT (organization_id, name, slug) ON schools TO apm_definer")
    op.execute("DROP POLICY schools_definer_select ON schools")
    op.execute(
        "CREATE POLICY schools_definer_select ON schools FOR SELECT TO apm_definer "
        f"USING ({_from_the_central('organization_id')} OR EXISTS "
        "(SELECT 1 FROM public.memberships m WHERE m.school_id = schools.id))"
    )
    op.execute(
        "CREATE POLICY schools_definer_insert ON schools FOR INSERT TO apm_definer "
        f"WITH CHECK ({_from_the_central('organization_id')})"
    )

    # The triggers of a new school (settings, default categories, audit rows) run as the caller.
    op.execute("GRANT INSERT (school_id, organization_id) ON school_settings TO apm_definer")
    op.execute(
        "CREATE POLICY school_settings_definer_insert ON school_settings FOR INSERT TO apm_definer "
        f"WITH CHECK ({_from_the_central('organization_id')})"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, key, name, applies_to, report_group, requires_approval) "
        "ON categories TO apm_definer"
    )
    op.execute(
        "CREATE POLICY categories_definer_insert ON categories FOR INSERT TO apm_definer "
        f"WITH CHECK ({_from_the_central('organization_id')})"
    )
    op.execute(
        "GRANT INSERT (organization_id, school_id, action, entity_type, entity_id, entity_reference, "
        "before_data, after_data) ON audit_logs TO apm_definer"
    )
    op.execute(
        "CREATE POLICY audit_logs_definer_insert ON audit_logs FOR INSERT TO apm_definer "
        f"WITH CHECK ({_from_the_central('organization_id')})"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    for ddl, signature in (
        (PROVISION, "provision_forklin_school(uuid, text, text)"),
        (SIGN_IN, "sso_sign_in(uuid, uuid, text, text, text)"),
    ):
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO apm_app")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")


def downgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute("DROP FUNCTION IF EXISTS public.sso_sign_in(uuid, uuid, text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS public.provision_forklin_school(uuid, text, text)")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")

    op.execute("SET LOCAL ROLE apm_owner")
    for policy, table in (
        ("audit_logs_definer_insert", "audit_logs"),
        ("categories_definer_insert", "categories"),
        ("school_settings_definer_insert", "school_settings"),
        ("schools_definer_insert", "schools"),
        ("organizations_definer_insert", "organizations"),
        ("memberships_definer_update", "memberships"),
        ("users_definer_link", "users"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    op.execute("REVOKE INSERT ON audit_logs FROM apm_definer")
    op.execute("REVOKE INSERT ON categories FROM apm_definer")
    op.execute("REVOKE INSERT ON school_settings FROM apm_definer")
    op.execute("REVOKE INSERT ON schools FROM apm_definer")
    op.execute("DROP POLICY schools_definer_select ON schools")
    op.execute(
        "CREATE POLICY schools_definer_select ON schools FOR SELECT TO apm_definer "
        "USING (EXISTS (SELECT 1 FROM public.memberships m WHERE m.school_id = schools.id))"
    )
    op.execute("REVOKE INSERT ON organizations FROM apm_definer")
    op.execute("REVOKE SELECT (central_org_id) ON organizations FROM apm_definer")
    op.execute("DROP POLICY organizations_definer_select ON organizations")
    op.execute(
        "CREATE POLICY organizations_definer_select ON organizations FOR SELECT TO apm_definer "
        "USING (EXISTS (SELECT 1 FROM public.memberships m WHERE m.organization_id = organizations.id))"
    )
    op.execute("REVOKE UPDATE (role, updated_at) ON memberships FROM apm_definer")
    op.execute("DROP POLICY users_definer_insert ON users")
    op.execute(
        "CREATE POLICY users_definer_insert ON users FOR INSERT TO apm_definer "
        "WITH CHECK (is_active AND password_hash IS NOT NULL)"
    )
    op.execute("REVOKE UPDATE (central_user_id, updated_at) ON users FROM apm_definer")
    op.execute("REVOKE INSERT (central_user_id) ON users FROM apm_definer")
    op.execute("REVOKE SELECT (central_user_id) ON users FROM apm_definer")
    op.execute("DROP INDEX IF EXISTS uq_organizations_central_org_id")
    op.execute("DROP INDEX IF EXISTS uq_users_central_user_id")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS central_org_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS central_user_id")
    op.execute("RESET ROLE")
