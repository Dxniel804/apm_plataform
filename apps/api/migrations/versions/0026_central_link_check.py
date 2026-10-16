# ruff: noqa: E501
"""is this person one of the Central's? one read-only SECURITY DEFINER function (docs/adr-forklin-sso.md, sections 7 and 8)

Revision ID: 0026_central_link_check
Revises: 0025_forklin_revocation
Create Date: 2026-10-16

With the Central ON, people are registered only there and enter only through it: the password of a
person who has a `central_user_id` must not open a session, and the "forgot the password" flow must
neither mint nor spend a reset for them. Before there is a session the application cannot read
`users.central_user_id` (row level security is forced and there is no school context), so the
check is one narrow, read-only function of apm_definer:

* `is_central_linked(user_id, email)` is true when a user matching the id, or the e-mail (case
  insensitive), carries a `central_user_id`. Either argument may be NULL. It reads no column the
  definer did not already have (id, email, central_user_id) and changes nothing.

The perimeter grows by exactly this one function (EXECUTE only for the application role); no table,
column grant or policy changes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_central_link_check"
down_revision: str | None = "0025_forklin_revocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SIGNATURE = "is_central_linked(uuid, text)"

CHECK = """
CREATE FUNCTION public.is_central_linked(p_user_id uuid, p_email text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
    SELECT EXISTS (
        SELECT 1 FROM public.users u
         WHERE u.central_user_id IS NOT NULL
           AND (u.id = p_user_id OR lower(u.email) = lower(p_email)))
$fn$
"""


def upgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(CHECK)
    op.execute(f"REVOKE ALL ON FUNCTION public.{SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.{SIGNATURE} TO apm_app")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")


def downgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute(f"DROP FUNCTION IF EXISTS public.{SIGNATURE}")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")
