# ruff: noqa: E501
"""two roles only: secretaria and staff (funcionario)

Revision ID: 0022_two_roles
Revises: 0021_password_reset
Create Date: 2026-10-15

The owner of the product decided on 2026-10-15 that a school has two roles, plus the families (which
have no login): the SECRETARIA (what was called "gestao" or treasurer, and now also reopens a month)
and the FUNCIONARIO (`staff`, unchanged). There is no school director above her and no read-only role.

* `school_admin` and `treasurer` become `secretaria`.
* `viewer` becomes `staff` but SUSPENDED (nobody gains access they did not have; the secretaria
  may bring them back as employees from the team screen). A live invitation for a viewer is revoked.
* The two CHECK constraints (`memberships.role`, `invitations.role`) accept only the new roles.

Row level security is FORCED, so even the owner sees no rows: it is switched off for the length of
this transaction on the two tables, the data is converted and it is switched on again.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_two_roles"
down_revision: str | None = "0021_password_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = "'secretaria', 'staff'"
OLD = "'school_admin', 'treasurer', 'staff', 'viewer'"


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for table in ("memberships", "invitations"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT ck_{table}_role_valid")
    op.execute(
        "UPDATE memberships SET status = 'suspended', updated_at = now() "
        "WHERE role = 'viewer' AND status = 'active'"
    )
    op.execute("UPDATE memberships SET role = 'staff' WHERE role = 'viewer'")
    op.execute(
        "UPDATE memberships SET role = 'secretaria' WHERE role IN ('school_admin', 'treasurer')"
    )
    op.execute(
        "UPDATE invitations SET revoked_at = now(), updated_at = now() "
        "WHERE role = 'viewer' AND accepted_at IS NULL AND revoked_at IS NULL"
    )
    op.execute("UPDATE invitations SET role = 'staff' WHERE role = 'viewer'")
    op.execute(
        "UPDATE invitations SET role = 'secretaria' WHERE role IN ('school_admin', 'treasurer')"
    )
    for table in ("memberships", "invitations"):
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_role_valid CHECK (role IN ({NEW}))"
        )
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("RESET ROLE")


def downgrade() -> None:
    # What was a school director or a viewer is not known any more: every secretaria goes back to
    # the old "treasurer" (the management); the schema accepts the old roles again.
    op.execute("SET LOCAL ROLE apm_owner")
    for table in ("memberships", "invitations"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT ck_{table}_role_valid")
        op.execute(f"UPDATE {table} SET role = 'treasurer' WHERE role = 'secretaria'")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_role_valid CHECK (role IN ({OLD}))"
        )
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("RESET ROLE")
