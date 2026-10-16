import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.organization import SLUG_PATTERN


class School(TimestampMixin, Base):
    __tablename__ = "schools"
    __table_args__ = (
        # slug is globally unique: the public portal resolves a school by /apm/{slug} (ADR-010).
        UniqueConstraint("slug"),
        # Target of the composite foreign keys (school_id, organization_id).
        UniqueConstraint("id", "organization_id", name="uq_schools_id_organization_id"),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="slug_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("slug_changes >= 0", name="slug_changes_not_negative"),
        Index("ix_schools_organization_id", "organization_id"),
        # One school per organization (ADR-020): the organization is the account of that school, so
        # a context that names only the organization can never see another school.
        Index("uq_schools_organization_id", "organization_id", unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    # How many times the address was changed and when last: written by the database (a trigger),
    # never by the application. Two free changes; from the third, 15 days after the previous one.
    slug_changes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    slug_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SchoolSlugHistory(Base):
    """Every address a school ever had (the current one included): one namespace for all schools,
    so an address is never given to another school and an old link keeps opening its school."""

    __tablename__ = "school_slug_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "organization_id"],
            ["schools.id", "schools.organization_id"],
            ondelete="RESTRICT",
            name="fk_school_slug_history_school_id_organization_id_schools",
        ),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="slug_format"),
        Index("ix_school_slug_history_school_id", "school_id"),
    )

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    school_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
