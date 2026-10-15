"""The `state` of "Entrar com Forklin": a random value kept in a cookie and returned by the App.

It stops somebody from pushing to a browser a return it did not start. A return that begins in the
App ("Acessar") has no state: the App cannot know it, so that flow is accepted without one (the same
accepted risk as the Diario Digital); the code is single use and lives 60 seconds.
"""

import hmac
import secrets

STATE_TTL_SECONDS = 600


def new_state() -> str:
    return secrets.token_urlsafe(32)


def state_is_valid(cookie_value: str | None, param_value: str | None) -> bool:
    """True when there is nothing to check (no cookie and no parameter) or both are the same."""
    if not cookie_value and not param_value:
        return True
    if not cookie_value or not param_value:
        return False
    return hmac.compare_digest(cookie_value.encode(), param_value.encode())
