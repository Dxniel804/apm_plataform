import uuid

from sqlalchemy import CheckConstraint, Index, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, uuid_pk

SLUG_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$"


class Organization(TimestampMixin, Base):
    """The tenant. A school is a sub-scope of an organization."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug"),
        # The organization in the Forklin Central this account belongs to (0023).
        Index("uq_organizations_central_org_id", "central_org_id", unique=True),
        CheckConstraint(f"slug ~ '{SLUG_PATTERN}'", name="slug_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("environment IN ('sandbox', 'production')", name="environment_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    # Only the SSO functions of apm_definer read it; the application role does not.
    central_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, deferred=True)
    # `sandbox` (demonstration) or `production`, as the Central says (0033). Only the definer
    # function `set_forklin_environment` changes it; the application role cannot.
    environment: Mapped[str] = mapped_column(Text, server_default="sandbox")
