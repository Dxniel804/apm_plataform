"""Settings of the receipt reading (OCR), read from the environment.

The model runs in ANOTHER container (`apps/ocr`) on a private network: the API only asks it, over
HTTP, for the text and the fields of a photo. Nothing here loads a model.
"""

from functools import lru_cache
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_TOKEN_LENGTH = 24


class OcrSettings(BaseSettings):
    """`OCR_ENABLED` turns the feature on; then `OCR_URL` (the service, e.g. http://ocr:8080) and
    `OCR_TOKEN` (the secret both sides share, at least 24 characters) are required."""

    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    ocr_enabled: bool = False
    ocr_url: str = ""
    ocr_token: SecretStr = SecretStr("")
    # The model may be slow on a CPU: the whole request is bounded by this.
    ocr_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    # How many readings run at once in this process, and how many a person may ask per minute.
    ocr_max_concurrency: int = Field(default=1, ge=1, le=8)
    ocr_user_per_minute: int = Field(default=6, ge=1, le=120)

    @model_validator(mode="after")
    def _enabled_needs_a_service(self) -> Self:
        if not self.ocr_enabled:
            return self
        parts = urlsplit(self.ocr_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("OCR_URL must be an http(s) URL when OCR_ENABLED is true")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("OCR_URL must be only scheme://host[:port][/path]")
        if len(self.ocr_token.get_secret_value()) < MIN_TOKEN_LENGTH:
            raise ValueError(f"OCR_TOKEN must have at least {MIN_TOKEN_LENGTH} characters")
        return self


@lru_cache
def get_ocr_settings() -> OcrSettings:
    return OcrSettings()
