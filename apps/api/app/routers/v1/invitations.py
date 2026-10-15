"""POST /invitations (administrators) and POST /invitations/accept (the invitee)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth import passwords
from app.auth.deps import Db, OptionalPrincipal, Principal, Settings, public, require
from app.auth.identity import accept_invitation, list_memberships
from app.auth.invite import issue_invitation
from app.auth.permissions import Permission
from app.auth.ratelimit import attempt_keys, blocked_for, client_ip, record_attempt
from app.auth.responses import membership_out, problem_responses
from app.auth.tokens import hash_token, looks_like_a_token
from app.core.errors import ProblemError
from app.db.request_context import bind_request_context
from app.schemas.auth import (
    AcceptedInvitationOut,
    AcceptInvitationRequest,
    InvitationOut,
    InvitationRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _ip(request: Request) -> str:
    return client_ip(request.client.host if request.client else None)


def _invalid() -> ProblemError:
    # One answer for every reason: unknown, already used, revoked, expired, malformed.
    return ProblemError(400, "invitation_invalid", "This invitation is not valid")


def _field_error(field: str, code: str) -> ProblemError:
    return ProblemError(
        422, "validation_error", "Invalid request", errors=[{"field": field, "code": code}]
    )


@router.post(
    "",
    operation_id="invitations_create",
    summary="Invite someone to the active organization or school",
    status_code=201,
    response_model=InvitationOut,
    responses=problem_responses(401, 403, 409, 422),
    openapi_extra={"x-permission": Permission.INVITATIONS_CREATE.value},
)
def create_invitation(
    body: InvitationRequest,
    principal: Annotated[Principal, Depends(require(Permission.INVITATIONS_CREATE))],
    db: Db,
    settings: Settings,
) -> InvitationOut:
    """The tenant is the one of the ACTIVE membership; nothing about it comes from the body. A
    school admin invites into its own school, and only into it (ADR-020). The token travels by
    e-mail and is never in the response."""
    return issue_invitation(
        db, settings, principal, email=body.email, role=body.role, school_id=body.school_id
    )


@router.post(
    "/accept",
    operation_id="invitations_accept",
    summary="Accept an invitation",
    status_code=201,
    response_model=AcceptedInvitationOut,
    responses=problem_responses(
        403,
        409,
        422,
        429,
        extra={400: {"description": "invitation_invalid (one answer for every reason)"}},
    ),
    dependencies=[Depends(public())],
)
def accept(
    body: AcceptInvitationRequest,
    request: Request,
    principal: OptionalPrincipal,
    db: Db,
    settings: Settings,
) -> AcceptedInvitationOut:
    """The token is the credential. A NEW person sends full_name and password and gets an account;
    someone who already has one must be LOGGED IN (the token alone never lets anybody act as an
    existing account) and sends only the token. Every failure looks the same."""
    bind_request_context(db, actor_type="PUBLIC" if principal is None else None)
    ip = _ip(request)
    # Keyed by IP alone: guessing tokens must not be able to lock other people out.
    keys = attempt_keys(settings.auth_secret, ip, ip)
    wait = blocked_for(db, "invitation", keys)
    if wait:
        db.commit()
        raise ProblemError(
            429,
            "rate_limited",
            "Too many attempts, try again later",
            headers={"Retry-After": str(wait)},
        )

    if principal is None and body.password is not None:
        problem = passwords.password_problem(body.password)
        if problem is not None:
            db.commit()
            raise ProblemError(
                422,
                "weak_password",
                "The password is not acceptable",
                errors=[{"field": "password", "code": problem}],
            )
    password_hash = (
        passwords.hash_password(body.password) if principal is None and body.password else None
    )

    result = None
    if looks_like_a_token(body.token):
        result = accept_invitation(
            db,
            hash_token(body.token),
            body.full_name,
            password_hash,
            None if principal is None else principal.user_id,
        )
    succeeded = result is not None and result.outcome.startswith("accepted_")
    record_attempt(db, "invitation", keys, succeeded=succeeded)
    if result is None or result.outcome == "invalid":
        db.commit()
        raise _invalid()
    if result.outcome == "login_required":
        db.commit()
        raise ProblemError(
            409,
            "account_exists_login_required",
            "That e-mail already has an account: log in and accept the invitation again",
        )
    if result.user_id is None or result.membership_id is None:
        raise _invalid()
    memberships = list_memberships(db, result.user_id)
    db.commit()
    created = next((m for m in memberships if m.membership_id == result.membership_id), None)
    if created is None:  # cannot happen (just created, active), but never answer with a guess
        raise _invalid()
    return AcceptedInvitationOut(user_id=result.user_id, membership=membership_out(created))
