"""The reading of a receipt photo, behind an interface (like `AttachmentStore`).

`HttpOcrProvider` asks the OCR container; `FakeOcrProvider` answers without a model (development and
tests). Whatever a provider returns is DATA FROM OUTSIDE: `app.ocr.service` validates every field
before the site sees it, and the answer is only ever a suggestion for a form.
"""

import http.client
import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.ocr.config import OcrSettings

# The service answers a small JSON; anything bigger is not it.
MAX_RESPONSE_BYTES = 64 * 1024


class OcrUnavailableError(Exception):
    """The service is off, unreachable, refused us or did not answer its contract."""


class OcrTimeoutError(Exception):
    """The reading took longer than the limit."""


@dataclass(frozen=True)
class RawField:
    value: Any
    confidence: float = 0.0


@dataclass(frozen=True)
class RawExtraction:
    """What a provider says, before validation: field name -> value and confidence."""

    fields: dict[str, RawField] = field(default_factory=dict)
    model: str = ""
    elapsed_ms: int = 0


class OcrProvider(Protocol):
    def extract(self, image: bytes, content_type: str) -> RawExtraction:
        """Read the photo. Raises `OcrUnavailableError` or `OcrTimeoutError`; never returns text."""
        ...


class FakeOcrProvider:
    """A reading without a model: a fixed answer, or `answer` when given (development, tests)."""

    def __init__(self, answer: RawExtraction | None = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[int, str]] = []
        self._answer = answer or RawExtraction(
            fields={
                "total_cents": RawField(8750, 0.95),
                "date": RawField("2026-09-10", 0.9),
                "merchant": RawField("PAPELARIA CENTRAL LTDA", 0.7),
                "document_number": RawField("12.345.678/0001-90", 0.85),
            },
            model="fake",
            elapsed_ms=1,
        )
        self._error = error

    def extract(self, image: bytes, content_type: str) -> RawExtraction:
        self.calls.append((len(image), content_type))
        if self._error is not None:
            raise self._error
        return self._answer


class HttpOcrProvider:
    """Asks `POST {OCR_URL}/v1/extract`: the image as the body, the shared token as a bearer.

    Standard library only (no extra dependency, no redirect following, no proxy from the
    environment): the service is on a private network and answers a few hundred bytes of JSON.
    """

    def __init__(self, settings: OcrSettings) -> None:
        parts = urlsplit(settings.ocr_url)
        self._https = parts.scheme == "https"
        self._host = parts.hostname or ""
        self._port = parts.port or (443 if self._https else 80)
        self._path = parts.path.rstrip("/") + "/v1/extract"
        self._token = settings.ocr_token.get_secret_value()
        self._timeout = settings.ocr_timeout_seconds

    def _connection(self) -> http.client.HTTPConnection:
        if self._https:
            return http.client.HTTPSConnection(self._host, self._port, timeout=self._timeout)
        return http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)

    def extract(self, image: bytes, content_type: str) -> RawExtraction:
        connection = self._connection()
        try:
            connection.request(
                "POST",
                self._path,
                body=image,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(image)),
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
        except TimeoutError:
            raise OcrTimeoutError from None
        except (OSError, http.client.HTTPException):
            raise OcrUnavailableError from None
        finally:
            connection.close()
        if status != 200 or len(body) > MAX_RESPONSE_BYTES:
            raise OcrUnavailableError
        return _parse(body)


def _parse(body: bytes) -> RawExtraction:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise OcrUnavailableError from None
    if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
        raise OcrUnavailableError
    fields: dict[str, RawField] = {}
    for name, item in data["fields"].items():
        if not isinstance(name, str) or not isinstance(item, dict):
            continue
        confidence = item.get("confidence")
        fields[name] = RawField(
            item.get("value"),
            float(confidence)
            if isinstance(confidence, int | float) and not isinstance(confidence, bool)
            else 0.0,
        )
    model = data.get("model")
    elapsed = data.get("elapsed_ms")
    return RawExtraction(
        fields=fields,
        model=model[:80] if isinstance(model, str) else "",
        elapsed_ms=elapsed if isinstance(elapsed, int) and not isinstance(elapsed, bool) else 0,
    )
