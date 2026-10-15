# ruff: noqa: E501
"""password reset: one table and two SECURITY DEFINER functions (docs/adr-password-reset.md)

Revision ID: 0021_password_reset
Revises: 0020_payment_providers
Create Date: 2026-10-15

Somebody who forgot the password has no session, so row level security shows nothing: like the
login and the invitation, this needs narrow functions of apm_definer. The perimeter grows by one
table (the app role has NO access to it) and two functions; the password itself is changed by the
API with the policy the logged-in user already has.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_password_reset"
down_revision: str | None = "0020_payment_providers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVE = "used_at IS NULL AND expires_at > now()"

REQUEST = """
CREATE FUNCTION public.request_password_reset(p_email text, p_token_hash bytea, p_minutes integer)
RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE
    found_user uuid;
BEGIN
    IF p_minutes IS NULL OR p_minutes < 1 OR p_minutes > 120 THEN
        RETURN false;
    END IF;
    SELECT u.id INTO found_user
      FROM public.users u
     WHERE lower(u.email) = lower(p_email) AND u.is_active
     LIMIT 1;
    IF found_user IS NULL THEN
        RETURN false;
    END IF;
    -- A new request cancels the ones still alive: only the last link works.
    UPDATE public.password_reset_tokens SET used_at = now()
     WHERE user_id = found_user AND used_at IS NULL AND expires_at > now();
    INSERT INTO public.password_reset_tokens (user_id, token_hash, expires_at)
    VALUES (found_user, p_token_hash, now() + make_interval(mins => p_minutes));
    RETURN true;
EXCEPTION WHEN unique_violation THEN
    RETURN false;
END
$fn$
"""

CONSUME = """
CREATE FUNCTION public.consume_password_reset(p_token_hash bytea)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE
    owner uuid;
BEGIN
    -- Row level security shows only live tokens: every reason for failure is "no row".
    UPDATE public.password_reset_tokens t SET used_at = now()
     WHERE t.token_hash = p_token_hash
       AND EXISTS (SELECT 1 FROM public.users u WHERE u.id = t.user_id AND u.is_active)
    RETURNING t.user_id INTO owner;
    RETURN owner;
END
$fn$
"""


def upgrade() -> None:
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute(
        """
        CREATE TABLE password_reset_tokens (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL,
            token_hash bytea NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_password_reset_tokens PRIMARY KEY (id),
            CONSTRAINT fk_password_reset_tokens_user_id_users
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_password_reset_tokens_token_hash UNIQUE (token_hash),
            CONSTRAINT ck_password_reset_tokens_hash_is_a_sha256 CHECK (octet_length(token_hash) = 32),
            CONSTRAINT ck_password_reset_tokens_expires_after_creation CHECK (expires_at > created_at)
        )
        """
    )
    op.execute("CREATE INDEX ix_password_reset_tokens_user_id ON password_reset_tokens (user_id)")
    op.execute("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE password_reset_tokens FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON password_reset_tokens FROM PUBLIC")
    op.execute(
        "GRANT SELECT (user_id, token_hash, expires_at, used_at), "
        "INSERT (user_id, token_hash, expires_at), UPDATE (used_at) "
        "ON password_reset_tokens TO apm_definer"
    )
    # An UPDATE also checks the NEW row against the SELECT policy, and a spent token is no longer
    # "live": the select policy lets spent-but-unexpired rows through, and only the UPDATE policy
    # (and the functions) are restricted to live tokens.
    op.execute(
        "CREATE POLICY password_reset_tokens_definer_select ON password_reset_tokens FOR SELECT TO apm_definer USING (expires_at > now())"
    )
    op.execute(
        "CREATE POLICY password_reset_tokens_definer_insert ON password_reset_tokens FOR INSERT TO apm_definer "
        "WITH CHECK (used_at IS NULL AND expires_at > now() AND expires_at <= now() + interval '2 hours')"
    )
    op.execute(
        f"CREATE POLICY password_reset_tokens_definer_update ON password_reset_tokens FOR UPDATE TO apm_definer "
        f"USING ({LIVE}) WITH CHECK (used_at IS NOT NULL)"
    )
    # The attempts and the sessions learn the new reasons.
    op.execute("ALTER TABLE login_attempts DROP CONSTRAINT ck_login_attempts_kind_valid")
    op.execute(
        "ALTER TABLE login_attempts ADD CONSTRAINT ck_login_attempts_kind_valid CHECK (kind IN "
        "('login', 'password', 'invitation', 'public_contribution', 'public_token', 'webhook', 'password_reset'))"
    )
    op.execute("ALTER TABLE sessions DROP CONSTRAINT ck_sessions_revoked_reason_valid")
    op.execute(
        "ALTER TABLE sessions ADD CONSTRAINT ck_sessions_revoked_reason_valid CHECK (revoked_reason IS NULL OR "
        "revoked_reason IN ('logout', 'rotated', 'password_changed', 'password_reset', 'membership_inactive', 'user_inactive'))"
    )
    op.execute("RESET ROLE")

    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    for ddl, signature in (
        (REQUEST, "request_password_reset(text, bytea, integer)"),
        (CONSUME, "consume_password_reset(bytea)"),
    ):
        op.execute(ddl)
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO apm_app")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")


def downgrade() -> None:
    op.execute("GRANT USAGE, CREATE ON SCHEMA public TO apm_definer")
    op.execute("SET LOCAL ROLE apm_definer")
    op.execute("DROP FUNCTION IF EXISTS public.consume_password_reset(bytea)")
    op.execute("DROP FUNCTION IF EXISTS public.request_password_reset(text, bytea, integer)")
    op.execute("RESET ROLE")
    op.execute("REVOKE CREATE ON SCHEMA public FROM apm_definer")
    op.execute("SET LOCAL ROLE apm_owner")
    op.execute("DROP TABLE IF EXISTS password_reset_tokens")
    # Rows of the new kinds may exist and row level security hides them from the owner: the old
    # constraints come back NOT VALID (they bind every new row; old rows are not rechecked).
    op.execute("ALTER TABLE login_attempts DROP CONSTRAINT ck_login_attempts_kind_valid")
    op.execute(
        "ALTER TABLE login_attempts ADD CONSTRAINT ck_login_attempts_kind_valid CHECK (kind IN "
        "('login', 'password', 'invitation', 'public_contribution', 'public_token', 'webhook')) NOT VALID"
    )
    op.execute("ALTER TABLE sessions DROP CONSTRAINT ck_sessions_revoked_reason_valid")
    op.execute(
        "ALTER TABLE sessions ADD CONSTRAINT ck_sessions_revoked_reason_valid CHECK (revoked_reason IS NULL OR "
        "revoked_reason IN ('logout', 'rotated', 'password_changed', 'membership_inactive', 'user_inactive')) NOT VALID"
    )
    op.execute("RESET ROLE")
