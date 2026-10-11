"""The rules of the staff requests: who may do what, in which state.

The database enforces the states (the edges, the final states, what never changes) and who can be
named; this layer decides what the database cannot know: WHO acts (the author attaches and cancels,
the management starts and resolves) and answers with a stable `code`. `database_rules` is the net
under it, for a race or a rule nobody foresaw.

Every function takes the `SchoolScope` of the request (organization, school and user come from the
session) and commits its own transaction.
"""

import base64
import binascii
import datetime as dt
import hashlib
import re
import uuid
from typing import Any, BinaryIO

from sqlalchemy.orm import Session

from app.auth.permissions import Permission
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, not_found
from app.expenses.attachment_types import HEAD_BYTES, sniff
from app.expenses.db_errors import database_rules
from app.staff_requests import repository
from app.staff_requests.schemas import (
    RequestAttachmentOut,
    RequestCreate,
    RequestDetail,
    RequestPage,
    RequestSummary,
)
from app.storage import AttachmentStore
from app.storage.base import CHUNK_SIZE
from app.storage.uploads import TooLarge, clean_file_name, discard, limited_chunks

Row = repository.Row

MAX_ATTACHMENTS_PER_REQUEST = 6
# Only photos: the site takes them with the camera or from the gallery.
PHOTO_TYPES = ("image/png", "image/jpeg", "image/webp")
_PERIOD = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")


# --- errors ---------------------------------------------------------------------------------------


def _invalid(field: str, code: str) -> ProblemError:
    """A 422 shaped like the validation errors of the framework: the field and a fixed code."""
    return ProblemError(
        422, "validation_error", "Invalid request", errors=[{"field": field, "code": code}]
    )


def invalid_field(field: str, code: str) -> ProblemError:
    """The same 422, for the router (a field of a form it parses itself)."""
    return _invalid(field, code)


def _invalid_state(row: Row) -> ProblemError:
    return ProblemError(
        409,
        "invalid_state",
        "The request is in a state that does not allow this",
        detail=f"The request is {row['status']}.",
    )


def _author_only() -> ProblemError:
    return ProblemError(403, "author_only", "Only the author of the request can do this")


# --- reading --------------------------------------------------------------------------------------


def _reads_all(scope: SchoolScope) -> bool:
    return Permission.REQUESTS_READ_ALL in scope.permissions


def _summary(row: Row) -> RequestSummary:
    return RequestSummary.model_validate(dict(row))


def _detail(db: Session, scope: SchoolScope, row: Row) -> RequestDetail:
    attachments = [
        RequestAttachmentOut.model_validate(dict(attachment))
        for attachment in repository.attachments_of(db, scope.school_id, row["id"])
    ]
    return RequestDetail.model_validate({**dict(row), "attachments": attachments})


def _fetch(db: Session, scope: SchoolScope, request_id: uuid.UUID) -> Row:
    """The request, if this person may see it. The answer for "no such request", "another
    school's" and "somebody else's, and you read only your own" is the same 404."""
    rows = repository.search(db, scope.school_id, request_id=request_id, limit=1)
    if not rows:
        raise not_found()
    row = rows[0]
    if not _reads_all(scope) and row["author_user_id"] != scope.user_id:
        raise not_found()
    return row


def _load_for_update(db: Session, scope: SchoolScope, request_id: uuid.UUID) -> Row:
    """The same, but holding the lock of the row, and read again after waiting for it."""
    _fetch(db, scope, request_id)
    if not repository.lock_request(db, scope.school_id, request_id):
        raise not_found()
    return _fetch(db, scope, request_id)


def get_request(db: Session, scope: SchoolScope, request_id: uuid.UUID) -> RequestDetail:
    return _detail(db, scope, _fetch(db, scope, request_id))


def _encode_cursor(created_at: dt.datetime, request_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{request_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[dt.datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("ascii")
        stamp, request_id = raw.split("|")
        created_at = dt.datetime.fromisoformat(stamp)
        if created_at.tzinfo is None:
            raise ValueError("naive")
        return created_at, uuid.UUID(request_id)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _invalid("cursor", "invalid") from None


def _period_start(period: str | None) -> dt.date | None:
    if period is None:
        return None
    found = _PERIOD.fullmatch(period)
    if found is None:
        raise _invalid("period", "invalid")
    try:
        return dt.date(int(found.group(1)), int(found.group(2)), 1)
    except ValueError:
        raise _invalid("period", "invalid") from None


def list_requests(
    db: Session,
    scope: SchoolScope,
    *,
    status: str | None,
    category: str | None,
    period: str | None,
    cursor: str | None,
    limit: int,
) -> RequestPage:
    """Newest first. Whoever has `requests:read_all` sees every request of the school; everybody
    else sees the ones they wrote. `period` is a month (YYYY-MM) of the creation, in the time zone
    of the school."""
    rows = repository.search(
        db,
        scope.school_id,
        author_id=None if _reads_all(scope) else scope.user_id,
        status=status,
        category=category,
        period_start=_period_start(period),
        before=_decode_cursor(cursor),
        limit=limit + 1,
    )
    page = rows[:limit]
    more = len(rows) > limit
    return RequestPage(
        items=[_summary(row) for row in page],
        next_cursor=_encode_cursor(page[-1]["created_at"], page[-1]["id"]) if more else None,
    )


# --- writing --------------------------------------------------------------------------------------


def _audit(
    db: Session, scope: SchoolScope, request_id: uuid.UUID, action: str, **data: Any
) -> None:
    repository.audit_event(
        db,
        organization_id=scope.organization_id,
        school_id=scope.school_id,
        action=action,
        request_id=request_id,
        data=data,
    )


def create_request(db: Session, scope: SchoolScope, body: RequestCreate) -> RequestDetail:
    """Always OPEN. The author is the person of the session, never something from the body."""
    with database_rules(db):
        request_id = repository.insert_request(
            db,
            organization_id=scope.organization_id,
            school_id=scope.school_id,
            author_user_id=scope.user_id,
            category=body.category,
            title=body.title,
            description=body.description,
        )
        _audit(db, scope, request_id, "request.created", category=body.category, status="OPEN")
        db.commit()
    return get_request(db, scope, request_id)


def add_attachment(
    db: Session,
    scope: SchoolScope,
    store: AttachmentStore,
    request_id: uuid.UUID,
    *,
    file_name: str | None,
    stream: BinaryIO,
    max_bytes: int,
) -> RequestAttachmentOut:
    """Only the author, and only while the request is open. The type is read from the bytes (a
    photo), the size is bounded while streaming and the sha256 is computed on the way to the store.
    The bytes are stored first and the row after: if writing the row fails the file is removed; if
    the COMMIT fails it is kept (a row without its file is worse than a file without a row)."""
    with database_rules(db):
        row = _load_for_update(db, scope, request_id)
        if row["author_user_id"] != scope.user_id:
            raise _author_only()
        if row["status"] not in repository.OPEN_STATUSES:
            raise ProblemError(
                409,
                "attachments_closed",
                "Photos can only be attached while the request is open",
                detail=f"The request is {row['status']}.",
            )
        if row["attachments_count"] >= MAX_ATTACHMENTS_PER_REQUEST:
            raise ProblemError(409, "attachment_limit", "The request has too many photos")
        head = stream.read(max(CHUNK_SIZE, HEAD_BYTES))
        if not head:
            raise _invalid("file", "empty")
        attachment_type = sniff(head)
        if attachment_type is None or attachment_type.content_type not in PHOTO_TYPES:
            raise ProblemError(
                415, "attachment_type_not_allowed", "Only photos (PNG, JPEG, WebP) are accepted"
            )
        key = f"{scope.organization_id}/{scope.school_id}/requests/{request_id}/{uuid.uuid4().hex}"
        hasher = hashlib.sha256()
        try:
            size = store.put(key, limited_chunks(head, stream, hasher, max_bytes))
        except TooLarge:
            raise ProblemError(
                413, "payload_too_large", "The file is larger than the limit"
            ) from None
        try:
            created = repository.insert_attachment(
                db,
                organization_id=scope.organization_id,
                school_id=scope.school_id,
                request_id=request_id,
                storage_key=key,
                file_name=clean_file_name(file_name, attachment_type.extension),
                content_type=attachment_type.content_type,
                size_bytes=size,
                sha256=hasher.hexdigest(),
                uploaded_by_user_id=scope.user_id,
            )
            _audit(
                db,
                scope,
                request_id,
                "request.attachment_added",
                attachment_id=str(created["id"]),
                size_bytes=size,
            )
        except BaseException:
            discard(store, key)
            raise
        db.commit()  # a failure HERE keeps the file (see the docstring)
    return RequestAttachmentOut.model_validate(dict(created))


def attachment_for_download(
    db: Session, scope: SchoolScope, request_id: uuid.UUID, attachment_id: uuid.UUID
) -> Row:
    """The photo, for whoever can see its request; anyone else gets the 404."""
    _fetch(db, scope, request_id)
    attachment = repository.get_attachment(db, scope.school_id, request_id, attachment_id)
    if attachment is None:
        raise not_found()
    return attachment


def _require_status(row: Row, *allowed: str) -> None:
    if row["status"] not in allowed:
        raise _invalid_state(row)


def start(db: Session, scope: SchoolScope, request_id: uuid.UUID) -> RequestDetail:
    """The management took it: OPEN to IN_PROGRESS."""
    with database_rules(db):
        row = _load_for_update(db, scope, request_id)
        _require_status(row, "OPEN")
        if not repository.start(
            db, scope.school_id, request_id, scope.user_id, expected=row["status"]
        ):
            raise _invalid_state(row)
        _audit(db, scope, request_id, "request.started", status="IN_PROGRESS")
        db.commit()
    return get_request(db, scope, request_id)


def resolve(
    db: Session, scope: SchoolScope, request_id: uuid.UUID, note: str | None
) -> RequestDetail:
    """The management answered it: OPEN or IN_PROGRESS to RESOLVED, with a note the author reads."""
    with database_rules(db):
        row = _load_for_update(db, scope, request_id)
        _require_status(row, *repository.OPEN_STATUSES)
        if not repository.resolve(
            db, scope.school_id, request_id, scope.user_id, note, expected=row["status"]
        ):
            raise _invalid_state(row)
        _audit(db, scope, request_id, "request.resolved", status="RESOLVED", has_note=bool(note))
        db.commit()
    return get_request(db, scope, request_id)


def cancel(db: Session, scope: SchoolScope, request_id: uuid.UUID) -> RequestDetail:
    """The author withdrew it, while it is open."""
    with database_rules(db):
        row = _load_for_update(db, scope, request_id)
        if row["author_user_id"] != scope.user_id:
            raise _author_only()
        _require_status(row, *repository.OPEN_STATUSES)
        if not repository.cancel(db, scope.school_id, request_id, expected=row["status"]):
            raise _invalid_state(row)
        _audit(db, scope, request_id, "request.cancelled", status="CANCELLED")
        db.commit()
    return get_request(db, scope, request_id)
