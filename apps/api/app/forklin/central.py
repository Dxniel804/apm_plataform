"""Talking to the Central: exchange the one-time code, verify the signed token or event.

Nothing here logs an e-mail, a name, a token or the secret. Every failure is a `CentralError` whose
`code` is one of the words of `/login?erro=` (`org`, `acesso`, `cargo`, `conflito`, `expirado`,
`indisponivel`) and whose `reason` is short and has no personal data (it goes to the log only).
"""

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import ApiSettings

ISSUER = "forklin"
EXCHANGE_TIMEOUT_SECONDS = 5
JWKS_TIMEOUT_SECONDS = 5
JWKS_LIFESPAN_SECONDS = 300
# Only EdDSA: `none`, HS256 (a public key used as a secret) and every other algorithm are refused.
ALGORITHMS = ["EdDSA"]
EVENT_PRODUCT_CONTRACTED = "organization.product_contracted"
# The events that END the open sessions of one person (docs/adr-forklin-sso.md, section 9). The
# list is an ALLOWLIST: any other name is ignored. `organization.<status>` is one entry per status
# of the Central other than `active` (enum OrganizationStatus: suspended, inactive); a new status
# of the Central has to be added here.
REVOKING_EVENTS = frozenset(
    {
        "access.revoked",
        "access.suspended",
        "user.disabled",
        "access.role_changed",
        "organization.suspended",
        "organization.inactive",
        "product.inactive",
    }
)
MAX_EVENT_LIFETIME_SECONDS = 120


class CentralError(Exception):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class AccessClaims:
    sub: uuid.UUID
    org: uuid.UUID
    role: str
    email: str
    name: str
    org_name: str | None


@dataclass(frozen=True)
class CentralEvent:
    """A signed event whose signature, audience, issuer and lifetime were verified. `event` is the
    name as the Central sent it (the receiver decides what it does with it). `organization_id` and
    `user_id` are filled for the events this product handles (`user_id` only for revoking ones)."""

    event: str
    jti: str
    organization_id: uuid.UUID | None
    organization_name: str | None
    user_id: uuid.UUID | None


class MalformedEventError(CentralError):
    """The signature is right but the claims an event of this kind needs are missing or wrong."""


def _central_url(settings: ApiSettings) -> str:
    return (settings.api_central_url or "").rstrip("/")


def exchange_code(settings: ApiSettings, code: str) -> str:
    """The access token the Central gives for a launch code (server to server, with the secret)."""
    secret = settings.forklin_product_secret
    if secret is None:
        raise CentralError("indisponivel", "product secret missing")
    request = urllib.request.Request(  # noqa: S310  (the Central URL is configured and http(s) only)
        f"{_central_url(settings)}/launch-codes/exchange-product",
        data=json.dumps({"code": code}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret.get_secret_value()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=EXCHANGE_TIMEOUT_SECONDS) as response:  # noqa: S310
            body: Any = json.loads(response.read(65536))
    except urllib.error.HTTPError as error:
        detail = _error_code(error)
        reason = f"exchange failed: HTTP {error.code} {detail}".strip()
        if error.code >= 500 or error.code == 401 or detail == "credential_invalid":
            raise CentralError("indisponivel", reason) from None
        if error.code == 403:
            raise CentralError("org" if detail == "org_inactive" else "acesso", reason) from None
        raise CentralError("expirado", reason) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise CentralError("indisponivel", "the Central did not answer the exchange") from None
    token = body.get("access_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token:
        raise CentralError("indisponivel", "the exchange answered without a token")
    return token


def _error_code(error: urllib.error.HTTPError) -> str:
    try:
        body: Any = json.loads(error.read(4096))
    except (ValueError, OSError):
        return ""
    code = body.get("code") if isinstance(body, dict) else None
    # Untrusted text from the other side, only ever shown in the log: short and without spaces.
    return code[:40] if isinstance(code, str) and code.replace("_", "").isalnum() else ""


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(
        f"{url}/.well-known/jwks.json",
        cache_keys=True,
        lifespan=JWKS_LIFESPAN_SECONDS,
        timeout=JWKS_TIMEOUT_SECONDS,
    )


def _signing_key(settings: ApiSettings, token: str) -> Any:
    try:
        return _jwks_client(_central_url(settings)).get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError:
        raise CentralError("indisponivel", "the key set of the Central is unreachable") from None
    except jwt.PyJWTError:
        raise CentralError("expirado", "no key of the Central matches this token") from None


def _decode(settings: ApiSettings, token: str, required: list[str]) -> dict[str, Any]:
    key = _signing_key(settings, token)
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=settings.forklin_product_slug,
            issuer=ISSUER,
            options={"require": required},
        )
    except jwt.ExpiredSignatureError:
        raise CentralError("expirado", "token expired") from None
    except jwt.PyJWTError:
        raise CentralError(
            "expirado", "token refused (signature, audience, issuer or claims)"
        ) from None
    return claims


def _uuid(value: object, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise CentralError("indisponivel", f"{what} is not a UUID") from None


def _text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:limit] or None


def verify_access_token(settings: ApiSettings, token: str) -> AccessClaims:
    claims = _decode(settings, token, ["exp", "iat", "sub", "org", "role"])
    email = _text(claims.get("email"), 254)
    name = _text(claims.get("name"), 200)
    role = claims.get("role")
    if email is None or name is None or not isinstance(role, str):
        raise CentralError("indisponivel", "the token has no e-mail, name or role")
    return AccessClaims(
        sub=_uuid(claims["sub"], "sub"),
        org=_uuid(claims["org"], "org"),
        role=role,
        email=email.lower(),
        name=name,
        org_name=_text(claims.get("org_name"), 120),
    )


def verify_event(settings: ApiSettings, token: str) -> CentralEvent:
    claims = _decode(settings, token, ["exp", "iat", "jti", "event"])
    lifetime = int(claims["exp"]) - int(claims["iat"])
    if lifetime <= 0 or lifetime > MAX_EVENT_LIFETIME_SECONDS:
        raise CentralError("expirado", "event with a lifetime out of the accepted range")
    event = claims["event"]
    if not isinstance(event, str):
        raise CentralError("acesso", "event without a name")
    jti = str(claims["jti"])[:64]
    if event == EVENT_PRODUCT_CONTRACTED:
        return CentralEvent(
            event=event,
            jti=jti,
            organization_id=_uuid(claims.get("organization_id"), "organization_id"),
            organization_name=_text(claims.get("organization_name"), 120),
            user_id=None,
        )
    if event in REVOKING_EVENTS:
        try:
            organization_id = uuid.UUID(str(claims.get("organization_id")))
            user_id = uuid.UUID(str(claims.get("user_id")))
        except ValueError:
            raise MalformedEventError(
                "acesso", "revoking event without a valid organization_id and user_id"
            ) from None
        return CentralEvent(
            event=event,
            jti=jti,
            organization_id=organization_id,
            organization_name=None,
            user_id=user_id,
        )
    return CentralEvent(
        event=event, jti=jti, organization_id=None, organization_name=None, user_id=None
    )
