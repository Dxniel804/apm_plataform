"""two more payment providers the platform may be connected to: Asaas and Pagar.me

Revision ID: 0020_payment_providers
Revises: 0019_statement_formats
Create Date: 2026-10-15

The three tables that name the provider of a payment (`payment_accounts`, `pix_charges`,
`webhook_events`) accepted only the planned Banco do Brasil and the sandbox. The platform will be
connected to ONE real gateway; its name is allowed here ahead of time so that choosing it is a
matter of code and credentials, not of a schema change in the middle of the ensaio. Allowing a name
does not turn anything on: a real provider is served only with the kill switch PIX_LIVE_ENABLED
(see app/pix/provider.py).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_payment_providers"
down_revision: str | None = "0019_statement_formats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("payment_accounts", "pix_charges", "webhook_events")
BEFORE = "provider IN ('BB', 'SANDBOX')"
AFTER = "provider IN ('BB', 'SANDBOX', 'ASAAS', 'PAGARME')"


def _swap(condition: str) -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    for table in TABLES:
        name = f"ck_{table}_provider_valid"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")
    op.execute("RESET ROLE")


def upgrade() -> None:
    _swap(AFTER)


def downgrade() -> None:
    _swap(BEFORE)
