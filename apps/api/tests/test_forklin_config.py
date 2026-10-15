"""The settings of the entry through the Forklin Central: what is refused.

docs/adr-forklin-sso.md."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import ApiSettings
from tests.helpers import TEST_AUTH_SECRET, UNREACHABLE_DATABASE_URL

BASE: dict[str, Any] = {
    "env": "development",
    "database_url": UNREACHABLE_DATABASE_URL,
    "auth_secret": TEST_AUTH_SECRET,
    "cookie_secure": False,
}
PRODUCTION: dict[str, Any] = {
    **BASE,
    "env": "production",
    "cookie_secure": True,
    "public_origins": "https://apm.exemplo.com.br",
    "email_sender": "resend",
    "resend_api_key": "re_not_a_real_key",
    "mail_from": "APM <contato@exemplo.com.br>",
}
FORKLIN: dict[str, Any] = {
    "forklin_core_enabled": True,
    "api_central_url": "https://api.exemplo.com.br",
    "forklin_app_url": "https://app.exemplo.com.br",
    "forklin_product_secret": "a-product-secret",
}


def build(**values: Any) -> ApiSettings:
    return ApiSettings(_env_file=None, **values)  # type: ignore[call-arg]


def test_off_by_default_and_nothing_else_is_required() -> None:
    settings = build(**BASE)
    assert settings.forklin_core_enabled is False
    assert settings.forklin_product_slug == "apm-digital"


@pytest.mark.parametrize(
    "missing", ["api_central_url", "forklin_app_url", "forklin_product_secret"]
)
def test_turned_on_it_needs_the_three_values(missing: str) -> None:
    values = {**BASE, **FORKLIN, missing: None}
    with pytest.raises(ValidationError, match="FORKLIN_CORE_ENABLED needs"):
        build(**values)
    with pytest.raises(ValidationError, match="FORKLIN_CORE_ENABLED needs"):
        build(**{**values, missing: "  "})


@pytest.mark.parametrize(
    "bad",
    ["ftp://central", "not a url", "https://user:pw@central.example", "https://central/?a=1"],
)
def test_the_urls_must_be_plain_http_urls(bad: str) -> None:
    with pytest.raises(ValidationError, match="must be a"):
        build(**{**BASE, **FORKLIN, "api_central_url": bad})
    with pytest.raises(ValidationError, match="must be a"):
        build(**{**BASE, **FORKLIN, "forklin_app_url": bad})


def test_in_development_plain_http_is_fine() -> None:
    build(
        **{
            **BASE,
            **FORKLIN,
            "api_central_url": "http://localhost:8100",
            "forklin_app_url": "http://localhost:3100",
        }
    )


def test_in_production_the_browser_facing_url_must_be_https() -> None:
    with pytest.raises(ValidationError, match="FORKLIN_APP_URL must be https"):
        build(**{**PRODUCTION, **FORKLIN, "forklin_app_url": "http://app.exemplo.com.br"})


def test_in_production_the_central_url_is_https_or_a_private_service_name() -> None:
    build(**{**PRODUCTION, **FORKLIN})  # https: fine
    build(
        **{**PRODUCTION, **FORKLIN, "api_central_url": "http://api-central:8000"}
    )  # as the App does
    for bad in ("http://api.exemplo.com.br", "http://10.0.0.5:8000", "http://central.interno:8000"):
        with pytest.raises(ValidationError, match="API_CENTRAL_URL must be https"):
            build(**{**PRODUCTION, **FORKLIN, "api_central_url": bad})


def test_the_secret_is_not_in_the_repr() -> None:
    assert "a-product-secret" not in repr(build(**{**BASE, **FORKLIN}))
