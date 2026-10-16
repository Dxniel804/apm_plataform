"""The three SECURITY DEFINER functions of ADR-016, called by name with bound parameters.

They are the only way the application reads a user by e-mail, lists the memberships of a user, or
accepts an invitation, because none of those can happen inside a tenant context (there is none yet).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class LoginIdentity:
    user_id: UUID
    password_hash: str | None
    is_active: bool


@dataclass(frozen=True)
class MembershipRow:
    membership_id: UUID
    organization_id: UUID
    organization_name: str
    organization_slug: str
    school_id: UUID
    school_name: str
    school_slug: str
    role: str


@dataclass(frozen=True)
class AcceptResult:
    outcome: str
    user_id: UUID | None
    membership_id: UUID | None
    organization_id: UUID | None
    school_id: UUID | None
    role: str | None


def find_login_identity(db: Session, email: str) -> LoginIdentity | None:
    row = db.execute(
        text("SELECT user_id, password_hash, is_active FROM public.find_login_identity(:email)"),
        {"email": email},
    ).one_or_none()
    return None if row is None else LoginIdentity(row[0], row[1], row[2])


def request_password_reset(db: Session, email: str, token_hash: bytes, minutes: int) -> bool:
    """True when the e-mail has an active account and a link was made (see the password ADR)."""
    found: bool = db.execute(
        text("SELECT public.request_password_reset(:email, :hash, :minutes)"),
        {"email": email, "hash": token_hash, "minutes": minutes},
    ).scalar_one()
    return bool(found)


def consume_password_reset(db: Session, token_hash: bytes) -> UUID | None:
    """The user the live token belongs to (and the token is spent), or None for every other case."""
    found: UUID | None = db.execute(
        text("SELECT public.consume_password_reset(:hash)"), {"hash": token_hash}
    ).scalar_one()
    return found


def list_memberships(db: Session, user_id: UUID) -> list[MembershipRow]:
    rows = db.execute(
        text(
            "SELECT membership_id, organization_id, organization_name, organization_slug, "
            "school_id, school_name, school_slug, role "
            "FROM public.list_memberships_for_user(:user_id)"
        ),
        {"user_id": user_id},
    ).all()
    return [MembershipRow(*row) for row in rows]


def accept_invitation(
    db: Session,
    token_hash: bytes,
    full_name: str | None,
    password_hash: str | None,
    existing_user_id: UUID | None,
) -> AcceptResult:
    row = db.execute(
        text(
            "SELECT outcome, user_id, membership_id, organization_id, school_id, role "
            "FROM public.accept_invitation(:token_hash, :full_name, :password_hash, :existing)"
        ),
        {
            "token_hash": token_hash,
            "full_name": full_name,
            "password_hash": password_hash,
            "existing": existing_user_id,
        },
    ).one()
    return AcceptResult(*row)


@dataclass(frozen=True)
class SsoSignIn:
    outcome: str
    user_id: UUID | None
    membership_id: UUID | None


def sso_sign_in(
    db: Session,
    *,
    central_user_id: UUID,
    central_org_id: UUID,
    email: str,
    full_name: str,
    role: str,
) -> SsoSignIn:
    """Finds, links by e-mail or creates the person that the Central vouched for and makes sure of
    the membership (docs/adr-forklin-sso.md). The outcome is `ok` or the reason it was refused."""
    row = db.execute(
        text(
            "SELECT outcome, user_id, membership_id "
            "FROM public.sso_sign_in(:central_user, :central_org, :email, :full_name, :role)"
        ),
        {
            "central_user": central_user_id,
            "central_org": central_org_id,
            "email": email,
            "full_name": full_name,
            "role": role,
        },
    ).one()
    return SsoSignIn(*row)


@dataclass(frozen=True)
class ProvisionedSchool:
    organization_id: UUID
    school_id: UUID
    created: bool


def provision_forklin_school(
    db: Session, *, central_org_id: UUID, name: str, slug: str
) -> ProvisionedSchool | None:
    """The empty account (organization and school) of an organization of the Central, created if it
    does not exist yet. None when it could not be made (no free slug)."""
    row = db.execute(
        text(
            "SELECT organization_id, school_id, created "
            "FROM public.provision_forklin_school(:central_org, :name, :slug)"
        ),
        {"central_org": central_org_id, "name": name, "slug": slug},
    ).one_or_none()
    return None if row is None else ProvisionedSchool(*row)


def revoke_forklin_sessions(db: Session, *, central_user_id: UUID, central_org_id: UUID) -> int:
    """Ends every open session of the person the Central names, if they belong to that
    organization. How many were ended (0 for an unknown person, another organization, or none open);
    memberships, status and password are never touched (docs/adr-forklin-sso.md, section 9)."""
    revoked: int = db.execute(
        text("SELECT public.revoke_forklin_sessions(:central_user, :central_org)"),
        {"central_user": central_user_id, "central_org": central_org_id},
    ).scalar_one()
    return revoked
