"""The team of the school: /employees. The management brings its employees in, from here.

It is the LOCAL way (an invitation e-mail with a link to choose a password). The permission is the
one of inviting (`invitations:create`) and what a person may do to another is decided by
INVITABLE_ROLES: who may invite a role may also suspend and bring back that role, never oneself.
When the platform joins the Forklin ecosystem the e-mail becomes the one of the Forklin App and the
person enters by SSO (docs/forklin-employees.md); these routes and screens stay.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text

from app.auth.deps import Db, Principal, Settings, require
from app.auth.invite import issue_invitation
from app.auth.permissions import INVITABLE_ROLES, Permission
from app.auth.responses import problem_responses
from app.core.errors import ProblemError
from app.schemas.auth import (
    EmployeeCreate,
    InvitationOut,
    MemberOut,
    PendingInvitationOut,
    Role,
    TeamOut,
)

router = APIRouter(prefix="/employees", tags=["employees"])

Team = Annotated[Principal, Depends(require(Permission.INVITATIONS_CREATE))]
_PERMISSION = {"x-permission": Permission.INVITATIONS_CREATE.value}
_ERRORS = problem_responses(401, 403, 404, 409, 422)


def _manageable(principal: Principal) -> frozenset[str]:
    return INVITABLE_ROLES.get(principal.role or "", frozenset())


def _school(principal: Principal) -> UUID:
    if principal.active is None:  # require() already guarantees it
        raise ProblemError(409, "context_required", "Choose which school to act for")
    return principal.active.school_id


@router.get(
    "",
    operation_id="employees_list",
    summary="The people of the school and the invitations still waiting",
    response_model=TeamOut,
    responses=_ERRORS,
    openapi_extra=_PERMISSION,
)
def list_team(principal: Team, db: Db) -> TeamOut:
    school = _school(principal)
    manageable = _manageable(principal)
    members = db.execute(
        text(
            "SELECT m.id, u.id, u.full_name, u.email, m.role, m.status FROM memberships m "
            "JOIN users u ON u.id = m.user_id WHERE m.school_id = :school "
            "ORDER BY m.status <> 'active', lower(u.full_name), u.email"
        ),
        {"school": school},
    ).all()
    pending = db.execute(
        text(
            "SELECT id, email, role, expires_at FROM invitations WHERE school_id = :school "
            "AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > now() "
            "ORDER BY created_at DESC"
        ),
        {"school": school},
    ).all()
    return TeamOut(
        members=[
            MemberOut(
                membership_id=row[0],
                user_id=row[1],
                full_name=row[2],
                email=row[3],
                role=row[4],
                status=row[5],
                is_you=row[1] == principal.user_id,
                can_manage=row[4] in manageable and row[1] != principal.user_id,
            )
            for row in members
        ],
        pending=[
            PendingInvitationOut(
                id=row[0],
                email=row[1],
                role=row[2],
                expires_at=row[3],
                can_manage=row[2] in manageable,
            )
            for row in pending
        ],
    )


@router.post(
    "",
    operation_id="employees_create",
    summary="Bring a person in: an e-mail with a link to choose the password",
    status_code=201,
    response_model=InvitationOut,
    responses=_ERRORS,
    openapi_extra=_PERMISSION,
)
def create_employee(
    body: EmployeeCreate, principal: Team, db: Db, settings: Settings
) -> InvitationOut:
    """The e-mail names the person and says which APM invited. The role defaults to employee."""
    return issue_invitation(
        db,
        settings,
        principal,
        email=body.email,
        role=body.role,
        full_name=body.full_name,
    )


def _live_invitation(db: Db, principal: Principal, invitation_id: UUID) -> tuple[str, Role]:
    row = db.execute(
        text(
            "SELECT email, role FROM invitations WHERE id = :id AND school_id = :school "
            "AND accepted_at IS NULL AND revoked_at IS NULL"
        ),
        {"id": invitation_id, "school": _school(principal)},
    ).one_or_none()
    if row is None:
        raise ProblemError(404, "not_found", "Not found")
    if row[1] not in _manageable(principal):
        raise ProblemError(403, "permission_denied", "You may not do that to this role")
    return str(row[0]), row[1]


@router.post(
    "/invitations/{invitation_id}/resend",
    operation_id="employees_invitation_resend",
    summary="Send the invitation again (the previous link stops working)",
    status_code=201,
    response_model=InvitationOut,
    responses=_ERRORS,
    openapi_extra=_PERMISSION,
)
def resend_invitation(
    invitation_id: UUID, principal: Team, db: Db, settings: Settings
) -> InvitationOut:
    email, role = _live_invitation(db, principal, invitation_id)
    db.execute(
        text("UPDATE invitations SET revoked_at = now(), updated_at = now() WHERE id = :id"),
        {"id": invitation_id},
    )
    return issue_invitation(db, settings, principal, email=email, role=role)


@router.delete(
    "/invitations/{invitation_id}",
    operation_id="employees_invitation_cancel",
    summary="Cancel an invitation that was not accepted",
    status_code=204,
    responses=_ERRORS,
    openapi_extra=_PERMISSION,
)
def cancel_invitation(invitation_id: UUID, principal: Team, db: Db) -> Response:
    _live_invitation(db, principal, invitation_id)
    db.execute(
        text("UPDATE invitations SET revoked_at = now(), updated_at = now() WHERE id = :id"),
        {"id": invitation_id},
    )
    db.commit()
    return Response(status_code=204)


def _set_status(
    db: Db, principal: Principal, membership_id: UUID, *, to: str, was: str
) -> Response:
    changed = db.execute(
        text(
            "UPDATE memberships SET status = :to, updated_at = now() WHERE id = :id "
            "AND school_id = :school AND user_id <> :me AND status = :was AND role = ANY(:roles) "
            "RETURNING id"
        ),
        {
            "to": to,
            "was": was,
            "id": membership_id,
            "school": _school(principal),
            "me": principal.user_id,
            "roles": sorted(_manageable(principal)),
        },
    ).first()
    if changed is None:
        raise ProblemError(404, "not_found", "Not found")
    db.commit()
    return Response(status_code=204)


@router.post(
    "/{membership_id}/suspend",
    operation_id="employees_suspend",
    summary="Take the access away from a person (their sessions end on the next request)",
    status_code=204,
    responses=_ERRORS,
    openapi_extra=_PERMISSION,
)
def suspend(membership_id: UUID, principal: Team, db: Db) -> Response:
    return _set_status(db, principal, membership_id, to="suspended", was="active")


@router.post(
    "/{membership_id}/activate",
    operation_id="employees_activate",
    summary="Give the access back to a suspended person",
    status_code=204,
    responses=_ERRORS,
    openapi_extra=_PERMISSION,
)
def activate(membership_id: UUID, principal: Team, db: Db) -> Response:
    return _set_status(db, principal, membership_id, to="active", was="suspended")
