"""Validation of a reading and the way a photo goes to it.

What the OCR container says is untrusted data: each field is checked against what an expense can
hold (an amount in range, a date that is not absurd, a short clean text) and anything else is
dropped. The result is a suggestion for the form; the person confirms it, and the expense is still
validated by the same rules as one typed by hand.
"""

import datetime as dt
import hashlib
import io
import json
import re
import unicodedata
from typing import Any, BinaryIO

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.expenses.access import SchoolScope
from app.expenses.attachment_types import HEAD_BYTES, sniff
from app.ocr.limits import ConcurrencyGate
from app.ocr.provider import OcrProvider, OcrTimeoutError, OcrUnavailableError, RawExtraction
from app.ocr.schemas import FieldConfidence, OcrSuggestion
from app.storage.base import CHUNK_SIZE
from app.storage.uploads import TooLarge, limited_chunks

# Smaller than the 10^12 cents the ledger accepts: a receipt of a school is never a billion reais.
MAX_AMOUNT_CENTS = 100_000_000
MAX_PAST_DAYS = 3 * 366
MAX_FUTURE_DAYS = 1
MAX_VENDOR_LENGTH = 200
_DOCUMENT = re.compile(r"[0-9A-Za-z./\- ]{1,30}")


def _confidence(raw: RawExtraction, name: str) -> float:
    field = raw.fields.get(name)
    if field is None:
        return 0.0
    return round(min(1.0, max(0.0, field.confidence)), 2)


def _amount(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= MAX_AMOUNT_CENTS else None


def _date(value: Any, today: dt.date) -> dt.date | None:
    if isinstance(value, dt.date):
        found = value
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            found = dt.date.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if found > today + dt.timedelta(days=MAX_FUTURE_DAYS) or found < today - dt.timedelta(
        days=MAX_PAST_DAYS
    ):
        return None
    return found


def _clean_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(ch for ch in value if unicodedata.category(ch)[0] != "C")
    text = " ".join(text.split())[:limit].strip()
    return text or None


def _document(value: Any) -> str | None:
    text = _clean_text(value, 30)
    return text if text is not None and _DOCUMENT.fullmatch(text) else None


def to_suggestion(raw: RawExtraction, today: dt.date | None = None) -> OcrSuggestion:
    """Keep only what is valid; a field that fails is simply absent, with confidence zero."""
    day = today or dt.datetime.now(dt.UTC).date()
    values = {
        "amount": _amount(raw.fields["total_cents"].value) if "total_cents" in raw.fields else None,
        "date": _date(raw.fields["date"].value, day) if "date" in raw.fields else None,
        "vendor": _clean_text(raw.fields["merchant"].value, MAX_VENDOR_LENGTH)
        if "merchant" in raw.fields
        else None,
        "document": _document(raw.fields["document_number"].value)
        if "document_number" in raw.fields
        else None,
    }
    names = {
        "amount": "total_cents",
        "date": "date",
        "vendor": "merchant",
        "document": "document_number",
    }
    confidence = FieldConfidence(
        **{key: (_confidence(raw, names[key]) if values[key] is not None else 0.0) for key in names}
    )
    return OcrSuggestion(
        amount_cents=values["amount"],  # type: ignore[arg-type]
        occurred_on=values["date"],  # type: ignore[arg-type]
        vendor=values["vendor"],  # type: ignore[arg-type]
        document_number=values["document"],  # type: ignore[arg-type]
        confidence=confidence,
        model=_clean_text(raw.model, 80) or "",
        elapsed_ms=raw.elapsed_ms if 0 <= raw.elapsed_ms < 10**7 else 0,
    )


# --- the request -------------------------------------------------------------------------------

PHOTO_TYPES = ("image/png", "image/jpeg", "image/webp")
BUSY_RETRY_SECONDS = 5


def _audit(db: Session, scope: SchoolScope, **data: Any) -> None:
    """One event per reading, with sizes and field names only: never the photo, never its text. It
    has no expense yet (the person still has to confirm the suggestion), so no entity id."""
    db.execute(
        text(
            "INSERT INTO audit_logs (organization_id, school_id, action, entity_type, after_data) "
            "VALUES (:organization_id, :school_id, 'expense.ocr_requested', 'expense_ocr', "
            "CAST(:data AS jsonb))"
        ),
        {
            "organization_id": scope.organization_id,
            "school_id": scope.school_id,
            "data": json.dumps(data),
        },
    )
    db.commit()


def read_receipt(
    db: Session,
    scope: SchoolScope,
    provider: OcrProvider,
    gate: ConcurrencyGate,
    stream: BinaryIO,
    *,
    max_bytes: int,
) -> OcrSuggestion:
    """Read the photo that came in the request. Nothing is stored here: the person attaches the same
    photo to the expense through the usual upload, after confirming the suggestion."""
    head = stream.read(max(CHUNK_SIZE, HEAD_BYTES))
    if not head:
        raise ProblemError(
            422, "validation_error", "Invalid request", errors=[{"field": "file", "code": "empty"}]
        )
    kind = sniff(head)
    if kind is None or kind.content_type not in PHOTO_TYPES:
        raise ProblemError(
            415, "attachment_type_not_allowed", "Only photos (PNG, JPEG, WebP) can be read"
        )
    buffer = io.BytesIO()
    try:
        for chunk in limited_chunks(head, stream, hashlib.sha256(), max_bytes):
            buffer.write(chunk)
    except TooLarge:
        raise ProblemError(413, "payload_too_large", "The file is larger than the limit") from None
    image = buffer.getvalue()

    if not gate.acquire():
        raise ProblemError(
            503,
            "ocr_busy",
            "The reading is busy with other photos",
            headers={"Retry-After": str(BUSY_RETRY_SECONDS)},
        )
    try:
        raw = provider.extract(image, kind.content_type)
    except OcrTimeoutError:
        _audit(db, scope, outcome="timeout", size_bytes=len(image))
        raise ProblemError(
            504, "ocr_timeout", "The reading took too long: fill the expense by hand"
        ) from None
    except OcrUnavailableError:
        _audit(db, scope, outcome="unavailable", size_bytes=len(image))
        raise ProblemError(
            503, "ocr_unavailable", "The reading is not available: fill the expense by hand"
        ) from None
    finally:
        gate.release()

    suggestion = to_suggestion(raw)
    found = [
        name
        for name, value in (
            ("amount", suggestion.amount_cents),
            ("date", suggestion.occurred_on),
            ("vendor", suggestion.vendor),
            ("document", suggestion.document_number),
        )
        if value is not None
    ]
    _audit(
        db, scope, outcome="ok", size_bytes=len(image), fields_found=found, model=suggestion.model
    )
    return suggestion
