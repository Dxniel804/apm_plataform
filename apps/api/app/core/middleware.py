"""Request id and Origin checking.

RequestIdMiddleware gives every request a fresh id (never one taken from the client) used in the
problem+json, the X-Request-ID header and the database setting app.request_id (audit).

OriginCheckMiddleware rejects every state-changing request whose Origin is not one of the site's own
origins: the CSRF defence that also covers the pre-login routes, where there is no session to bind
a token to (login CSRF). When the Origin header is PRESENT it decides alone (`Origin: null`, which
sandboxed pages send, or a malformed value is a refusal, never a reason to look at the Referer); the
Referer is read only when there is no Origin header at all. Routes that legitimately receive calls
without a browser (webhooks, later) must be listed in ORIGIN_EXEMPT_PATHS and authenticate by a
secret.
"""

import uuid
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.csrf import SAFE_METHODS
from app.core.config import canonical_origin
from app.core.errors import ProblemError, problem_response

# The webhooks of the Pix provider are called by a server, not by a page: they have no Origin and
# authenticate by their own secret (X-Webhook-Secret).
ORIGIN_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/api/v1/webhooks/pix/sandbox", "/api/v1/webhooks/pix/bb"}
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response


def _origin_of(value: str | None) -> str | None:
    """The scheme://host[:port] of an Origin or Referer value, or None for anything unusable
    (empty, "null", not a URL, an unparsable host such as an unbalanced bracket)."""
    if not value:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return canonical_origin(parts.scheme, parts.netloc)


def _requesting_origin(request: Request) -> str | None:
    """The origin the request claims to come from: the Origin header when there is one (whatever
    it holds), the Referer only when there is no Origin header."""
    origin = request.headers.get("origin")
    if origin is not None:
        return _origin_of(origin)
    return _origin_of(request.headers.get("referer"))


class OriginCheckMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        allowed_origins: tuple[str, ...],
        exempt_paths: frozenset[str] = ORIGIN_EXEMPT_PATHS,
    ) -> None:
        super().__init__(app)
        self.allowed = frozenset(origin.lower() for origin in allowed_origins)
        self.exempt = exempt_paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in SAFE_METHODS and request.url.path not in self.exempt:
            origin = _requesting_origin(request)
            # "Origin: null" (sandboxed pages), a broken value and no header at all end up here.
            if origin is None or origin not in self.allowed:
                return problem_response(
                    request,
                    ProblemError(
                        403, "origin_not_allowed", "This request does not come from the site"
                    ),
                )
        return await call_next(request)


# The most a request may DECLARE before the route even reads it. A webhook is a few hundred bytes of
# JSON; everything else is at most a file (a statement PDF is the largest, 5 MiB) plus its form.
WEBHOOK_BODY_LIMIT = 64 * 1024
BODY_LIMIT = 24 * 1024 * 1024  # the database ceiling for one attachment is 20 MiB, plus the form


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """Refuses a request that DECLARES a body larger than any route accepts, before the body is
    read: without it, an unauthenticated caller could make the API parse a huge JSON (the webhook
    routes are public). A body that does not declare its length is still bounded by each route and
    by the reverse proxy in front of the API (set its maximum body size there too)."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None:
            limit = WEBHOOK_BODY_LIMIT if request.url.path in ORIGIN_EXEMPT_PATHS else BODY_LIMIT
            # Plain ASCII digits only (int() also reads "¹²" and refuses a huge string); a number
            # with more than 12 digits is larger than any limit without converting it.
            if (
                declared.isascii()
                and declared.isdigit()
                and (len(declared) > 12 or int(declared) > limit)
            ):
                return problem_response(
                    request, ProblemError(413, "payload_too_large", "The request is too large")
                )
        return await call_next(request)
