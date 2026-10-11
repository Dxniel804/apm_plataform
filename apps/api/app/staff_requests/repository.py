"""The SQL of the staff requests: constant statements, values always bound.

Every statement names the school (`school_id`) even though row level security already limits what
the session sees. Nothing here decides who may do what (the service does) or what the states allow
(the database does).
"""

import datetime as dt
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.orm import Session

Row = RowMapping

OPEN_STATUSES = ("OPEN", "IN_PROGRESS")


def insert_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    author_user_id: uuid.UUID,
    category: str,
    title: str,
    description: str | None,
) -> uuid.UUID:
    created: uuid.UUID = db.execute(
        text(
            "INSERT INTO staff_requests (organization_id, school_id, author_user_id, category, "
            "title, description) VALUES (:organization_id, :school_id, :author_user_id, "
            ":category, :title, :description) RETURNING id"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "author_user_id": author_user_id,
            "category": category,
            "title": title,
            "description": description,
        },
    ).scalar_one()
    return created


def search(
    db: Session,
    school_id: uuid.UUID,
    *,
    request_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None,
    status: str | None = None,
    category: str | None = None,
    period_start: dt.date | None = None,
    before: tuple[dt.datetime, uuid.UUID] | None = None,
    limit: int = 1,
) -> Sequence[Row]:
    """Requests of the school, newest first. One statement serves the list and the detail: a
    filter that is NULL does not apply. `before` is the keyset of the last row of the page."""
    return (
        db.execute(
            text(
                "SELECT r.id, r.category, r.title, r.description, r.status, r.author_user_id, "
                "r.started_at, r.started_by_user_id, r.resolved_at, r.resolved_by_user_id, "
                "r.resolution_note, r.created_at, r.updated_at, "
                "(SELECT count(*) FROM staff_request_attachments a "
                " WHERE a.request_id = r.id AND a.school_id = r.school_id) AS attachments_count "
                "FROM staff_requests r "
                "LEFT JOIN school_settings ss ON ss.school_id = r.school_id "
                "WHERE r.school_id = :school_id "
                "AND (CAST(:request_id AS uuid) IS NULL OR r.id = :request_id) "
                "AND (CAST(:author_id AS uuid) IS NULL OR r.author_user_id = :author_id) "
                "AND (CAST(:status AS text) IS NULL OR r.status = :status) "
                "AND (CAST(:category AS text) IS NULL OR r.category = :category) "
                "AND (CAST(:period_start AS date) IS NULL OR ("
                "r.created_at >= CAST(CAST(:period_start AS date) AS timestamp) "
                "AT TIME ZONE ss.timezone "
                "AND r.created_at < (CAST(:period_start AS date) + interval '1 month') "
                "AT TIME ZONE ss.timezone)) "
                "AND (CAST(:before_at AS timestamptz) IS NULL "
                "OR (r.created_at, r.id) < (CAST(:before_at AS timestamptz), "
                "CAST(:before_id AS uuid))) "
                "ORDER BY r.created_at DESC, r.id DESC LIMIT :limit"
            ),
            {
                "school_id": school_id,
                "request_id": request_id,
                "author_id": author_id,
                "status": status,
                "category": category,
                "period_start": period_start,
                "before_at": None if before is None else before[0],
                "before_id": None if before is None else before[1],
                "limit": limit,
            },
        )
        .mappings()
        .all()
    )


def lock_request(db: Session, school_id: uuid.UUID, request_id: uuid.UUID) -> bool:
    """Take the row lock of the request (waits for whoever holds it); False when there is none."""
    found = db.execute(
        text("SELECT 1 FROM staff_requests WHERE id = :id AND school_id = :school_id FOR UPDATE"),
        {"id": request_id, "school_id": school_id},
    ).first()
    return found is not None


def attachments_of(db: Session, school_id: uuid.UUID, request_id: uuid.UUID) -> Sequence[Row]:
    return (
        db.execute(
            text(
                "SELECT id, file_name, content_type, size_bytes, sha256, uploaded_by_user_id, "
                "created_at FROM staff_request_attachments "
                "WHERE school_id = :school_id AND request_id = :request_id "
                "ORDER BY created_at, id"
            ),
            {"school_id": school_id, "request_id": request_id},
        )
        .mappings()
        .all()
    )


def get_attachment(
    db: Session, school_id: uuid.UUID, request_id: uuid.UUID, attachment_id: uuid.UUID
) -> Row | None:
    return (
        db.execute(
            text(
                "SELECT id, storage_key, file_name, content_type, size_bytes, sha256 "
                "FROM staff_request_attachments WHERE id = :id AND school_id = :school_id "
                "AND request_id = :request_id"
            ),
            {"id": attachment_id, "school_id": school_id, "request_id": request_id},
        )
        .mappings()
        .one_or_none()
    )


def insert_attachment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    request_id: uuid.UUID,
    storage_key: str,
    file_name: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    uploaded_by_user_id: uuid.UUID,
) -> Row:
    return (
        db.execute(
            text(
                "INSERT INTO staff_request_attachments (organization_id, school_id, request_id, "
                "storage_key, file_name, content_type, size_bytes, sha256, uploaded_by_user_id) "
                "VALUES (:organization_id, :school_id, :request_id, :storage_key, :file_name, "
                ":content_type, :size_bytes, :sha256, :uploaded_by_user_id) RETURNING id, "
                "file_name, content_type, size_bytes, sha256, uploaded_by_user_id, created_at"
            ),
            {
                "organization_id": organization_id,
                "school_id": school_id,
                "request_id": request_id,
                "storage_key": storage_key,
                "file_name": file_name,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "uploaded_by_user_id": uploaded_by_user_id,
            },
        )
        .mappings()
        .one()
    )


def start(
    db: Session, school_id: uuid.UUID, request_id: uuid.UUID, user_id: uuid.UUID, *, expected: str
) -> bool:
    """OPEN -> IN_PROGRESS as a compare-and-swap: False when somebody else moved it first."""
    result = db.execute(
        text(
            "UPDATE staff_requests SET status = 'IN_PROGRESS', started_at = now(), "
            "started_by_user_id = :user_id, updated_at = now() "
            "WHERE id = :id AND school_id = :school_id AND status = :expected"
        ),
        {"id": request_id, "school_id": school_id, "user_id": user_id, "expected": expected},
    )
    return bool(result.rowcount == 1)  # type: ignore[attr-defined]


def resolve(
    db: Session,
    school_id: uuid.UUID,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    note: str | None,
    *,
    expected: str,
) -> bool:
    result = db.execute(
        text(
            "UPDATE staff_requests SET status = 'RESOLVED', resolved_at = now(), "
            "resolved_by_user_id = :user_id, resolution_note = :note, updated_at = now() "
            "WHERE id = :id AND school_id = :school_id AND status = :expected"
        ),
        {
            "id": request_id,
            "school_id": school_id,
            "user_id": user_id,
            "note": note,
            "expected": expected,
        },
    )
    return bool(result.rowcount == 1)  # type: ignore[attr-defined]


def cancel(db: Session, school_id: uuid.UUID, request_id: uuid.UUID, *, expected: str) -> bool:
    result = db.execute(
        text(
            "UPDATE staff_requests SET status = 'CANCELLED', updated_at = now() "
            "WHERE id = :id AND school_id = :school_id AND status = :expected"
        ),
        {"id": request_id, "school_id": school_id, "expected": expected},
    )
    return bool(result.rowcount == 1)  # type: ignore[attr-defined]


def audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    action: str,
    request_id: uuid.UUID,
    data: Mapping[str, Any],
) -> None:
    """A high-level event (`request.resolved`) next to the row changes the triggers record. The
    actor is NOT passed: the database takes it from the settings of the transaction. `data` holds
    ids and states only, never free text."""
    db.execute(
        text(
            "INSERT INTO audit_logs (organization_id, school_id, action, entity_type, entity_id, "
            "after_data) VALUES (:organization_id, :school_id, :action, 'staff_requests', "
            ":entity_id, CAST(:data AS jsonb))"
        ),
        {
            "organization_id": organization_id,
            "school_id": school_id,
            "action": action,
            "entity_id": request_id,
            "data": json.dumps(data),
        },
    )
