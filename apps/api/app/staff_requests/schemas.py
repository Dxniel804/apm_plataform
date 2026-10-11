"""The HTTP contract of the staff requests: snake_case, ISO 8601 instants, and the states and
categories of the database with no translation (the site translates them)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints

from app.schemas.auth import Strict, _storable

RequestCategory = Literal["SUPPLIES", "MAINTENANCE", "EVENT", "FINANCE", "OTHER"]
RequestStatus = Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]

# Stripped text of a length, and storable (no NUL byte, no lone surrogate). The constraints come
# BEFORE the check: a constraint written after a validator is not applied to the text.
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_storable),
]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    AfterValidator(_storable),
]
Note = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
    AfterValidator(_storable),
]


class RequestCreate(Strict):
    category: RequestCategory
    title: Title
    description: Description | None = None


class ResolveRequest(Strict):
    """What the management tells the author when it closes the request (optional)."""

    note: Note | None = None


class RequestAttachmentOut(BaseModel):
    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by_user_id: uuid.UUID
    created_at: dt.datetime


class RequestSummary(BaseModel):
    id: uuid.UUID
    category: RequestCategory
    title: str
    status: RequestStatus
    author_user_id: uuid.UUID
    attachments_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
    resolved_at: dt.datetime | None


class RequestDetail(RequestSummary):
    description: str | None
    started_at: dt.datetime | None
    started_by_user_id: uuid.UUID | None
    resolved_by_user_id: uuid.UUID | None
    resolution_note: str | None
    attachments: list[RequestAttachmentOut]


class RequestPage(BaseModel):
    items: list[RequestSummary]
    next_cursor: str | None
