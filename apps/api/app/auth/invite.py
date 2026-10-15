"""Making an invitation: the ONE place where a person is invited into the school of the inviter.

Used by `POST /invitations` and by the team routes (`/employees`). The tenant is the one of the
ACTIVE membership; nothing about it comes from the request. The token travels by e-mail and is
never returned.

This is the LOCAL way of bringing a person in (an e-mail with a link to choose a password). When the
platform joins the Forklin ecosystem the e-mail will be the one of the Forklin App and the person
will enter through SSO; the routes stay, only this function is replaced (docs/forklin-employees.md).
"""

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import Principal
from app.auth.emailer import build_sender, invitation_message
from app.auth.permissions import INVITABLE_ROLES
from app.auth.tokens import hash_token, new_token
from app.core.config import ApiSettings
from app.core.errors import ProblemError
from app.schemas.auth import InvitationOut, Role

logger = logging.getLogger(__name__)

INVITATION_LIFETIME_HOURS = 72


def _field_error(field: str, code: str) -> ProblemError:
    return ProblemError(
        422, "validation_error", "Invalid request", errors=[{"field": field, "code": code}]
    )


def issue_invitation(
    db: Session,
    settings: ApiSettings,
    principal: Principal,
    *,
    email: str,
    role: Role,
    school_id: UUID | None = None,
    full_name: str | None = None,
) -> InvitationOut:
    active = principal.active
    if active is None:  # require() already guarantees it; never rely on an assert for this
        raise ProblemError(
            409, "context_required", "Choose which school or organization to act for"
        )
    if role not in INVITABLE_ROLES.get(active.role, frozenset()):
        raise ProblemError(403, "permission_denied", "You may not invite that role")

    # Every membership is of ONE school, so an invitation always goes into the inviter's school. A
    # school_id in the body is only accepted when it is that same school.
    if school_id not in (None, active.school_id):
        raise ProblemError(403, "permission_denied", "You may only invite into your school")
    target = active.school_id

    # Visible only if it belongs to the active organization and school: row level security.
    found = db.execute(text("SELECT 1 FROM schools WHERE id = :id"), {"id": target}).first()
    if found is None:
        raise _field_error("school_id", "not_found")

    # An existing member of the SAME scope is visible to this tenant (never one of another tenant).
    already = db.execute(
        text(
            "SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id "
            "WHERE lower(u.email) = :email AND m.school_id = :school "
            "AND m.status IN ('active', 'invited', 'suspended')"
        ),
        {"email": email, "school": target},
    ).first()
    if already is not None:
        raise ProblemError(409, "already_member", "That person already has access here")

    # An expired invitation still occupies the "one live invitation per scope" slot: free it.
    db.execute(
        text(
            "UPDATE invitations SET revoked_at = now(), updated_at = now() "
            "WHERE email = :email AND school_id = :school "
            "AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at <= now()"
        ),
        {"email": email, "school": target},
    )

    token = new_token()
    try:
        row = db.execute(
            text(
                "INSERT INTO invitations (organization_id, school_id, email, role, token_hash, "
                "invited_by_user_id, expires_at) VALUES (:org, :school, :email, :role, :hash, "
                ":by, now() + make_interval(hours => :hours)) "
                "RETURNING id, expires_at"
            ),
            {
                "org": active.organization_id,
                "school": target,
                "email": email,
                "role": role,
                "hash": hash_token(token),
                "by": principal.user_id,
                "hours": INVITATION_LIFETIME_HOURS,
            },
        ).one()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ProblemError(
            409, "invitation_pending", "There is already a pending invitation for that person here"
        ) from None
    try:
        build_sender(settings).send(
            invitation_message(settings, email, token, active.organization_name, full_name)
        )
    except OSError:
        logger.warning("could not write the invitation e-mail to the outbox")
    return InvitationOut(id=row[0], email=email, role=role, school_id=target, expires_at=row[1])
