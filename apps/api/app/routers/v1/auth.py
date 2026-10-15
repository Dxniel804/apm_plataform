"""POST /auth/login, POST /auth/logout, GET /auth/me, POST /auth/context, POST /auth/password."""

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy import text

from app.auth import passwords
from app.auth import sessions as session_store
from app.auth.deps import Db, OptionalPrincipal, Principal, Settings, authenticated, public
from app.auth.emailer import build_sender, password_changed_message, password_reset_message
from app.auth.identity import (
    consume_password_reset,
    find_login_identity,
    list_memberships,
    request_password_reset,
)
from app.auth.ratelimit import attempt_keys, blocked_for, client_ip, record_attempt
from app.auth.responses import (
    clear_session_cookies,
    problem_responses,
    session_response,
    set_session_cookies,
)
from app.auth.tokens import hash_token, looks_like_a_token, new_token
from app.core.errors import ProblemError
from app.db.request_context import bind_request_context
from app.schemas.auth import (
    ContextRequest,
    LoginRequest,
    PasswordRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    SessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(request: Request) -> str:
    return client_ip(request.client.host if request.client else None)


def _user_agent_hash(request: Request) -> bytes | None:
    agent = request.headers.get("user-agent")
    return hashlib.sha256(agent.encode()).digest() if agent else None


def _rate_limited(seconds: int) -> ProblemError:
    return ProblemError(
        429,
        "rate_limited",
        "Too many attempts, try again later",
        headers={"Retry-After": str(seconds)},
    )


@router.post(
    "/login",
    operation_id="auth_login",
    summary="Log in with e-mail and password",
    response_model=SessionResponse,
    responses=problem_responses(401, 403, 422, 429),
    dependencies=[Depends(public())],
)
def login(
    body: LoginRequest, request: Request, response: Response, db: Db, settings: Settings
) -> SessionResponse:
    """Starts a session (a NEW token every time; one presented by the client is revoked, never
    reused). The answer for an unknown e-mail, a wrong password and an inactive account is the same
    problem, and a password verification is performed in every one of those cases."""
    bind_request_context(db, actor_type="PUBLIC")
    keys = attempt_keys(settings.auth_secret, body.email, _ip(request))
    wait = blocked_for(db, "login", keys)
    if wait:
        db.commit()
        raise _rate_limited(wait)

    identity = find_login_identity(db, body.email)
    stored = identity.password_hash if identity is not None and identity.is_active else None
    matched = passwords.check_password(stored, body.password)
    record_attempt(db, "login", keys, succeeded=matched)
    if not matched or identity is None:
        db.commit()
        raise ProblemError(401, "invalid_credentials", "Invalid e-mail or password")

    bind_request_context(db, user_id=identity.user_id)
    if stored is not None and passwords.needs_rehash(stored):
        db.execute(
            text("UPDATE users SET password_hash = :hash, updated_at = now() WHERE id = :id"),
            {"hash": passwords.hash_password(body.password), "id": identity.user_id},
        )
    presented = request.cookies.get(settings.session_cookie_name)
    if presented and looks_like_a_token(presented):
        # Session fixation: whatever token the client came with is ended, never adopted. Presenting
        # a token proves holding it, so it may end that session whoever it belonged to.
        previous = hash_token(presented)
        bind_request_context(db, session_id=previous)
        session_store.revoke_session(db, previous, "rotated")

    memberships = list_memberships(db, identity.user_id)
    active = memberships[0] if len(memberships) == 1 else None
    token = new_token()
    session_id = hash_token(token)
    expires_at = session_store.create_session(
        db,
        session_id=session_id,
        user_id=identity.user_id,
        membership_id=None if active is None else active.membership_id,
        ip=_ip(request),
        user_agent_hash=_user_agent_hash(request),
    )
    profile = db.execute(
        text("SELECT email, full_name FROM users WHERE id = :id"), {"id": identity.user_id}
    ).one()
    db.commit()
    set_session_cookies(response, settings, token, session_id, expires_at)
    return session_response(
        user_id=identity.user_id,
        email=profile[0],
        full_name=profile[1],
        memberships=memberships,
        active=active,
        session_id=session_id,
        expires_at=expires_at,
        settings=settings,
    )


@router.post(
    "/logout",
    operation_id="auth_logout",
    summary="End the session",
    status_code=204,
    responses=problem_responses(403),
    dependencies=[Depends(public())],
)
def logout(request: Request, principal: OptionalPrincipal, db: Db, settings: Settings) -> Response:
    """Idempotent: always 204 and the cookies are cleared. With a valid session it is revoked (the
    CSRF token is then required, so a foreign page cannot log the user out)."""
    if principal is not None:
        session_store.revoke_session(db, principal.session_id, "logout")
        db.commit()
    result = Response(status_code=204)
    clear_session_cookies(result, settings)
    return result


@router.get(
    "/me",
    operation_id="auth_me",
    summary="Who is logged in and where they act",
    response_model=SessionResponse,
    responses=problem_responses(401),
)
def me(
    principal: Annotated[Principal, Depends(authenticated())], settings: Settings
) -> SessionResponse:
    return session_response(
        user_id=principal.user_id,
        email=principal.email,
        full_name=principal.full_name,
        memberships=principal.memberships,
        active=principal.active,
        session_id=principal.session_id,
        expires_at=principal.expires_at,
        settings=settings,
    )


@router.post(
    "/context",
    operation_id="auth_switch_context",
    summary="Change the active membership (rotates the session token)",
    response_model=SessionResponse,
    responses=problem_responses(401, 403, 422),
)
def switch_context(
    body: ContextRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(authenticated())],
    db: Db,
    settings: Settings,
) -> SessionResponse:
    """Only among the user's OWN active memberships (an unknown id and somebody else's get the same
    answer). A new token is issued and the old session ended; the absolute expiry is kept."""
    target = next((m for m in principal.memberships if m.membership_id == body.membership_id), None)
    if target is None:
        raise ProblemError(403, "context_not_allowed", "That membership is not available to you")
    token = new_token()
    session_id = hash_token(token)
    expires_at = session_store.create_session(
        db,
        session_id=session_id,
        user_id=principal.user_id,
        membership_id=target.membership_id,
        ip=_ip(request),
        user_agent_hash=_user_agent_hash(request),
        expires_at=principal.expires_at,
    )
    session_store.revoke_session(db, principal.session_id, "rotated")
    db.commit()
    set_session_cookies(response, settings, token, session_id, expires_at)
    return session_response(
        user_id=principal.user_id,
        email=principal.email,
        full_name=principal.full_name,
        memberships=principal.memberships,
        active=target,
        session_id=session_id,
        expires_at=expires_at,
        settings=settings,
    )


@router.post(
    "/password",
    operation_id="auth_change_password",
    summary="Change the password (ends every session and starts a new one)",
    status_code=204,
    responses=problem_responses(401, 403, 422, 429),
)
def change_password(
    body: PasswordRequest,
    request: Request,
    principal: Annotated[Principal, Depends(authenticated())],
    db: Db,
    settings: Settings,
) -> Response:
    keys = attempt_keys(settings.auth_secret, str(principal.user_id), _ip(request))
    wait = blocked_for(db, "password", keys)
    if wait:
        db.commit()
        raise _rate_limited(wait)

    identity = find_login_identity(db, principal.email)
    stored = identity.password_hash if identity is not None else None
    matched = passwords.check_password(stored, body.current_password)
    record_attempt(db, "password", keys, succeeded=matched)
    if not matched:
        db.commit()
        raise ProblemError(403, "current_password_incorrect", "The current password is not correct")

    problem = passwords.password_problem(body.new_password)
    if problem is None and body.new_password == body.current_password:
        problem = "same_as_current"
    if problem is not None:
        db.commit()
        raise ProblemError(
            422,
            "weak_password",
            "The new password is not acceptable",
            errors=[{"field": "new_password", "code": problem}],
        )

    db.execute(
        text("UPDATE users SET password_hash = :hash, updated_at = now() WHERE id = :id"),
        {"hash": passwords.hash_password(body.new_password), "id": principal.user_id},
    )
    session_store.revoke_all_sessions(db, principal.user_id, "password_changed")
    token = new_token()
    session_id = hash_token(token)
    expires_at = session_store.create_session(
        db,
        session_id=session_id,
        user_id=principal.user_id,
        membership_id=None if principal.active is None else principal.active.membership_id,
        ip=_ip(request),
        user_agent_hash=_user_agent_hash(request),
        expires_at=principal.expires_at,
    )
    db.commit()
    try:
        # The audit of this event belongs to the financial task's audit log; the e-mail notice is
        # here. It never contains the password, and a failing outbox must not undo the change.
        build_sender(settings).send(password_changed_message(principal.email))
    except OSError:
        logger.warning("could not write the password-changed notice to the outbox")
    result = Response(status_code=204)
    set_session_cookies(result, settings, token, session_id, expires_at)
    return result


# --- forgot the password (docs/adr-password-reset.md) ---------------------------------------------

RESET_LINK_MINUTES = 30


def _send_reset_mail(settings: Settings, to: str, token: str) -> None:
    """After the answer left (a background task), so that the time of the answer does not tell
    whether the account exists. A failing sender is only logged."""
    try:
        build_sender(settings).send(password_reset_message(settings, to, token, RESET_LINK_MINUTES))
    except OSError:
        logger.warning("could not send the password reset e-mail")


@router.post(
    "/password-reset/request",
    operation_id="auth_password_reset_request",
    summary="Ask for a link to choose a new password (the answer is the same for any e-mail)",
    status_code=202,
    responses=problem_responses(422, 429),
    dependencies=[Depends(public())],
)
def password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: Db,
    settings: Settings,
) -> dict[str, str]:
    """Always 202, whether the e-mail has an account or not. The attempts are counted per e-mail and
    per address BEFORE anything else, so the limit is the same for every e-mail."""
    bind_request_context(db, actor_type="PUBLIC")
    keys = attempt_keys(settings.auth_secret, body.email, _ip(request))
    wait = blocked_for(db, "password_reset", keys)
    if wait:
        db.commit()
        raise _rate_limited(wait)
    # Every request counts as an attempt (a "failure" for the limiter); a few are free.
    record_attempt(db, "password_reset", keys, succeeded=False)
    token = new_token()
    made = request_password_reset(db, body.email, hash_token(token), RESET_LINK_MINUTES)
    db.commit()
    if made:
        background.add_task(_send_reset_mail, settings, body.email, token)
    return {"status": "accepted"}


@router.post(
    "/password-reset/confirm",
    operation_id="auth_password_reset_confirm",
    summary="Choose the new password with the link of the e-mail (ends every session)",
    status_code=204,
    responses=problem_responses(
        422,
        429,
        extra={400: {"description": "reset_invalid (one answer for every reason)"}},
    ),
    dependencies=[Depends(public())],
)
def password_reset_confirm(
    body: PasswordResetConfirm,
    request: Request,
    background: BackgroundTasks,
    db: Db,
    settings: Settings,
) -> Response:
    """The token is the credential. Everything happens in ONE transaction: the token is spent, the
    password is changed and every session ends; if any step fails nothing is kept."""
    bind_request_context(db, actor_type="PUBLIC")
    ip = _ip(request)
    # Keyed by the address alone: guessing tokens must not be able to lock other people out.
    keys = attempt_keys(settings.auth_secret, ip, ip)
    wait = blocked_for(db, "password_reset", keys)
    if wait:
        db.commit()
        raise _rate_limited(wait)
    problem = passwords.password_problem(body.new_password)
    if problem is not None:
        db.commit()
        raise ProblemError(
            422,
            "weak_password",
            "The new password is not acceptable",
            errors=[{"field": "new_password", "code": problem}],
        )
    user_id = (
        consume_password_reset(db, hash_token(body.token))
        if looks_like_a_token(body.token)
        else None
    )
    record_attempt(db, "password_reset", keys, succeeded=user_id is not None)
    if user_id is None:
        db.commit()
        raise ProblemError(400, "reset_invalid", "This link is not valid")
    bind_request_context(db, user_id=user_id)
    db.execute(
        text("UPDATE users SET password_hash = :hash, updated_at = now() WHERE id = :id"),
        {"hash": passwords.hash_password(body.new_password), "id": user_id},
    )
    session_store.revoke_all_sessions(db, user_id, "password_reset")
    email: str = db.execute(
        text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
    ).scalar_one()
    db.commit()
    background.add_task(_send_changed_notice, settings, email)
    return Response(status_code=204)


def _send_changed_notice(settings: Settings, to: str) -> None:
    try:
        build_sender(settings).send(password_changed_message(to))
    except OSError:
        logger.warning("could not send the password-changed notice")
