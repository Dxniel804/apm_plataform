"""Staff requests (migration 0012): a collaborator asks the management for something, with photos.

Not money, so outside the ledger, but a tenant table like the others: the constraints here mirror
the migration and carry the same names; triggers, policies and grants live only in the migration.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.financial_common import (
    HEX64,
    ScopeMixin,
    fin_pk,
    in_list,
    scope_constraints,
    user_fk,
)

REQUEST_CATEGORIES = ("SUPPLIES", "MAINTENANCE", "EVENT", "FINANCE", "OTHER")
REQUEST_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED")
IMAGE_CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")


class StaffRequest(ScopeMixin, Base):
    __tablename__ = "staff_requests"
    __table_args__ = (
        *scope_constraints("staff_requests"),
        user_fk("staff_requests", "author_user_id"),
        user_fk("staff_requests", "started_by_user_id"),
        user_fk("staff_requests", "resolved_by_user_id"),
        UniqueConstraint(
            "id",
            "organization_id",
            "school_id",
            name="uq_staff_requests_id_organization_id_school_id",
        ),
        CheckConstraint(in_list("category", REQUEST_CATEGORIES), name="category_valid"),
        CheckConstraint(in_list("status", REQUEST_STATUSES), name="status_valid"),
        CheckConstraint("length(btrim(title)) BETWEEN 1 AND 120", name="title_length"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000", name="description_length"
        ),
        CheckConstraint(
            "resolution_note IS NULL OR length(btrim(resolution_note)) BETWEEN 1 AND 1000",
            name="resolution_note_length",
        ),
        CheckConstraint(
            "(started_at IS NULL) = (started_by_user_id IS NULL)", name="started_has_a_person"
        ),
        CheckConstraint(
            "(resolved_at IS NULL) = (resolved_by_user_id IS NULL)", name="resolved_has_a_person"
        ),
        CheckConstraint(
            "(status = 'RESOLVED') = (resolved_at IS NOT NULL)", name="resolved_iff_status"
        ),
        CheckConstraint(
            "resolution_note IS NULL OR status = 'RESOLVED'", name="note_only_when_resolved"
        ),
        Index(
            "ix_staff_requests_school_id_created_at",
            "school_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index("ix_staff_requests_school_id_status", "school_id", "status"),
        Index("ix_staff_requests_school_id_author_user_id", "school_id", "author_user_id"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    author_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    category: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'OPEN'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffRequestAttachment(ScopeMixin, Base):
    """A photo of a request. Insert-only; the bytes live behind a storage key."""

    __tablename__ = "staff_request_attachments"
    __table_args__ = (
        *scope_constraints("staff_request_attachments"),
        ForeignKeyConstraint(
            ["request_id", "organization_id", "school_id"],
            ["staff_requests.id", "staff_requests.organization_id", "staff_requests.school_id"],
            name="fk_staff_request_attachments_request_id_staff_requests",
            ondelete="RESTRICT",
        ),
        user_fk("staff_request_attachments", "uploaded_by_user_id"),
        UniqueConstraint(
            "school_id",
            "request_id",
            "sha256",
            name="uq_staff_request_attachments_school_id_request_id_sha256",
        ),
        CheckConstraint(
            "length(storage_key) BETWEEN 1 AND 500 AND storage_key !~ '^/'",
            name="storage_key_length",
        ),
        CheckConstraint("length(btrim(file_name)) BETWEEN 1 AND 255", name="file_name_length"),
        CheckConstraint(in_list("content_type", IMAGE_CONTENT_TYPES), name="content_type_image"),
        CheckConstraint("size_bytes BETWEEN 1 AND 20971520", name="size_range"),
        CheckConstraint(f"sha256 ~ '{HEX64}'", name="sha256_format"),
        Index("ix_staff_request_attachments_request_id", "request_id"),
        Index("ix_staff_request_attachments_school_id", "school_id"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    storage_key: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
