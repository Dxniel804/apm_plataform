"""The Forklin Central: "Entrar com Forklin" (SSO) and the notice of a new organization.

GET  /forklin/sso/start      sends the browser to the App with a `state`
GET  /forklin/sso/callback   the App/Central returns here with a one-time `code`
POST /forklin/events         the Central, server to server: an organization contracted this product,
                             or somebody's access ended (their open sessions are ended at once)

Everything answers 404 unless FORKLIN_CORE_ENABLED (docs/adr-forklin-sso.md). The sign-in ends in
the SAME session the password login makes (same cookie, same CSRF), so nothing else of the
product knows the difference. Every refusal goes back to /login?erro=<word>; the reason only
reaches the log, with no e-mail, name, token or secret.
"""

import hashlib
import logging
import re
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import RedirectResponse

from app.auth import sessions as session_store
from app.auth.deps import Db, Settings, public
from app.auth.identity import provision_forklin_school, revoke_forklin_sessions, sso_sign_in
from app.auth.ratelimit import client_ip
from app.auth.responses import problem_responses, set_session_cookies
from app.auth.tokens import hash_token, looks_like_a_token, new_token
from app.core.errors import ProblemError
from app.db.request_context import bind_request_context
from app.forklin import central
from app.forklin.central import CentralError, MalformedEventError
from app.forklin.roles import local_role, school_name, school_slug
from app.forklin.state import STATE_TTL_SECONDS, new_state, state_is_valid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forklin", tags=["forklin"])

LANDING = "/painel"


def _state_cookie(settings: Settings) -> str:
    return "__Host-apm_sso_state" if settings.cookie_secure else "apm_sso_state"


def _enabled(settings: Settings) -> None:
    if not settings.forklin_core_enabled:
        raise ProblemError(404, "not_found", "Not found")


def _redirect(location: str, settings: Settings, *, drop_state: bool) -> RedirectResponse:
    response = RedirectResponse(location, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    if drop_state:
        response.delete_cookie(_state_cookie(settings), path="/", secure=settings.cookie_secure)
    return response


def _refuse(settings: Settings, code: str, reason: str, *, drop_state: bool) -> RedirectResponse:
    # Only the word and a short reason: never an e-mail, a name, a token or the secret.
    logger.warning("sso refused: erro=%s reason=%s", code, reason)
    return _redirect(f"/login?{urlencode({'erro': code})}", settings, drop_state=drop_state)


@router.get(
    "/sso/start",
    operation_id="forklin_sso_start",
    summary="Go to the Forklin App to sign in",
    status_code=302,
    responses=problem_responses(404),
    dependencies=[Depends(public())],
)
def sso_start(settings: Settings) -> Response:
    _enabled(settings)
    app_url = (settings.forklin_app_url or "").rstrip("/")
    state = new_state()
    query = urlencode({"produto": settings.forklin_product_slug, "state": state})
    response = _redirect(f"{app_url}/entrar?{query}", settings, drop_state=False)
    response.set_cookie(
        _state_cookie(settings),
        state,
        max_age=STATE_TTL_SECONDS,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get(
    "/sso/callback",
    operation_id="forklin_sso_callback",
    summary="Finish the sign-in the Central vouched for",
    status_code=302,
    responses=problem_responses(404, 422),
    dependencies=[Depends(public())],
)
def sso_callback(
    request: Request,
    db: Db,
    settings: Settings,
    code: Annotated[str | None, Query(max_length=512)] = None,
    state: Annotated[str | None, Query(max_length=512)] = None,
) -> Response:
    _enabled(settings)
    from_button = _state_cookie(settings) in request.cookies
    if not code:
        return _refuse(settings, "expirado", "no code", drop_state=from_button)
    if not state_is_valid(request.cookies.get(_state_cookie(settings)), state):
        return _refuse(settings, "expirado", "state missing or different", drop_state=from_button)

    try:
        token = central.exchange_code(settings, code)
        claims = central.verify_access_token(settings, token)
    except CentralError as error:
        return _refuse(settings, error.code, error.reason, drop_state=from_button)
    role = local_role(claims.role)
    if role is None:
        return _refuse(
            settings, "cargo", "a role the product does not know", drop_state=from_button
        )

    bind_request_context(db, actor_type="PUBLIC")
    signed = sso_sign_in(
        db,
        central_user_id=claims.sub,
        central_org_id=claims.org,
        email=claims.email,
        full_name=claims.name,
        role=role,
    )
    if signed.outcome == "org_unknown" and role == "secretaria":
        # The notice of the contract did not arrive (or has not yet): the first secretaria to come
        # makes the empty account. An employee never does: the school has to exist first.
        name = school_name(claims.org_name)
        provision_forklin_school(
            db,
            central_org_id=claims.org,
            name=name,
            slug=school_slug(name, str(claims.org)),
        )
        signed = sso_sign_in(
            db,
            central_user_id=claims.sub,
            central_org_id=claims.org,
            email=claims.email,
            full_name=claims.name,
            role=role,
        )
    if signed.outcome != "ok" or signed.user_id is None or signed.membership_id is None:
        db.rollback()
        word = {"conflict": "conflito", "org_unknown": "org"}.get(signed.outcome, "acesso")
        return _refuse(settings, word, f"sign-in outcome {signed.outcome}", drop_state=from_button)

    bind_request_context(db, user_id=signed.user_id)
    presented = request.cookies.get(settings.session_cookie_name)
    if presented and looks_like_a_token(presented):
        # Session fixation: a token the browser came with is ended, never adopted.
        previous = hash_token(presented)
        bind_request_context(db, session_id=previous)
        session_store.revoke_session(db, previous, "rotated")
    session_token = new_token()
    session_id = hash_token(session_token)
    agent = request.headers.get("user-agent")
    expires_at = session_store.create_session(
        db,
        session_id=session_id,
        user_id=signed.user_id,
        membership_id=signed.membership_id,
        ip=client_ip(request.client.host if request.client else None),
        user_agent_hash=hashlib.sha256(agent.encode()).digest() if agent else None,
    )
    db.commit()
    response = _redirect(LANDING, settings, drop_state=from_button)
    set_session_cookies(response, settings, session_token, session_id, expires_at)
    return response


class EventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=8192)


class EventAccepted(BaseModel):
    status: str


def _loggable(name: str) -> str:
    # The name comes inside a token the Central signed, but the log gets a plain word or nothing.
    return name if re.fullmatch(r"[a-z_]{1,40}(\.[a-z_]{1,40}){0,2}", name) else "(unreadable)"


@router.post(
    "/events",
    operation_id="forklin_events",
    summary="The Central tells this product something that happened to an organization or a person",
    response_model=EventAccepted,
    responses=problem_responses(
        401,
        404,
        422,
        extra={
            400: {
                "description": "invalid_event (signed, but missing the person or the organization)"
            }
        },
    ),
    dependencies=[Depends(public())],
)
def receive_event(body: EventBody, db: Db, settings: Settings) -> EventAccepted:
    """Server to server: no Origin, no session. The signed token IS the authentication (EdDSA key
    of the Central, audience of this product, a lifetime of two minutes). What happens next depends
    on the event, from an ALLOWLIST:

    * `organization.product_contracted` makes the empty account (idempotent);
    * the revoking events (`central.REVOKING_EVENTS`) end the open sessions of that one person. An
      unknown person, or one of another organization, is a no-op that answers exactly like a hit;
    * any other name is ignored (200, so that the Central does not retry for ever).
    """
    _enabled(settings)
    try:
        event = central.verify_event(settings, body.token)
    except MalformedEventError as error:
        logger.warning("forklin event malformed: %s", error.reason)
        raise ProblemError(
            400, "invalid_event", "The event is missing something it needs"
        ) from None
    except CentralError as error:
        logger.warning("forklin event refused: %s", error.reason)
        raise ProblemError(401, "invalid_event", "The event could not be verified") from None
    bind_request_context(db, actor_type="SYSTEM")

    if event.event == central.EVENT_PRODUCT_CONTRACTED and event.organization_id is not None:
        name = school_name(event.organization_name)
        result = provision_forklin_school(
            db,
            central_org_id=event.organization_id,
            name=name,
            slug=school_slug(name, str(event.organization_id)),
        )
        if result is None:
            db.rollback()
            raise ProblemError(409, "provision_failed", "The account could not be created")
        db.commit()
        return EventAccepted(status="created" if result.created else "exists")

    if event.event in central.REVOKING_EVENTS and event.user_id and event.organization_id:
        revoked = revoke_forklin_sessions(
            db, central_user_id=event.user_id, central_org_id=event.organization_id
        )
        db.commit()
        # Only the name of the event and a count: never who it was about.
        logger.info("forklin event %s: %d session(s) ended", _loggable(event.event), revoked)
        return EventAccepted(status="processed")

    logger.info("forklin event ignored: %s", _loggable(event.event))
    return EventAccepted(status="ignored")
