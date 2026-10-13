"""The settings of the reading: off by default; on only with a service and a real secret."""

import pytest
from pydantic import ValidationError

from app.ocr.config import OcrSettings


def make(**values: object) -> OcrSettings:
    return OcrSettings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def test_it_is_off_by_default_and_needs_nothing() -> None:
    settings = make()

    assert settings.ocr_enabled is False
    assert settings.ocr_max_concurrency == 1 and settings.ocr_timeout_seconds == 30


def test_on_with_a_service_and_a_secret() -> None:
    settings = make(ocr_enabled=True, ocr_url="http://ocr:8080", ocr_token="s" * 24)

    assert settings.ocr_url == "http://ocr:8080"


@pytest.mark.parametrize(
    "values",
    [
        {"ocr_url": "", "ocr_token": "s" * 24},
        {"ocr_url": "ftp://ocr:8080", "ocr_token": "s" * 24},
        {"ocr_url": "http://", "ocr_token": "s" * 24},
        {"ocr_url": "http://user:pw@ocr:8080", "ocr_token": "s" * 24},
        {"ocr_url": "http://ocr:8080/?x=1", "ocr_token": "s" * 24},
        {"ocr_url": "http://ocr:8080", "ocr_token": ""},
        {"ocr_url": "http://ocr:8080", "ocr_token": "short"},
    ],
)
def test_on_without_a_valid_service_or_secret_it_refuses_to_start(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        make(ocr_enabled=True, **values)


@pytest.mark.parametrize(
    "field", ["ocr_timeout_seconds", "ocr_max_concurrency", "ocr_user_per_minute"]
)
def test_the_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        make(**{field: 0})


def test_the_runtime_of_the_process_follows_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default dependency (not an override): off without settings, a real provider with them.
    It is built once and kept, because the limits live in it."""
    from app.ocr.config import get_ocr_settings
    from app.ocr.provider import HttpOcrProvider
    from app.ocr.router import get_ocr_runtime

    def fresh() -> object:
        get_ocr_settings.cache_clear()
        get_ocr_runtime.cache_clear()
        return get_ocr_runtime()

    monkeypatch.delenv("OCR_ENABLED", raising=False)
    off = fresh()
    assert off.provider is None  # type: ignore[attr-defined]
    monkeypatch.setenv("OCR_ENABLED", "true")
    monkeypatch.setenv("OCR_URL", "http://ocr:8080")
    monkeypatch.setenv("OCR_TOKEN", "k" * 32)
    on = fresh()
    assert isinstance(on.provider, HttpOcrProvider)  # type: ignore[attr-defined]
    assert get_ocr_runtime() is on  # one per process
    get_ocr_settings.cache_clear()
    get_ocr_runtime.cache_clear()
