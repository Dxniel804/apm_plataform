"""Campaigns (migration 0013): products the management sells to the families, with a cart.

A campaign has a cover and products; an order of a family is a contribution whose amount is the sum
of what it bought, kept as a copy (`contribution_items`) so a price changed later never touches an
order already made. The constraints here mirror the migration and carry the same names; triggers,
policies and grants live only in the migration.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
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
from app.models.financial_common import (
    HEX64,
    ScopeMixin,
    fin_pk,
    in_list,
    scope_constraints,
    user_fk,
)

CAMPAIGN_STATUSES = ("DRAFT", "ACTIVE", "ENDED")
IMAGE_CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")


def _image_checks(prefix: str) -> tuple[CheckConstraint, ...]:
    """All five columns of an image or none, and each one inside its limits."""
    return (
        CheckConstraint(
            f"({prefix}_storage_key IS NULL) = ({prefix}_content_type IS NULL) "
            f"AND ({prefix}_storage_key IS NULL) = ({prefix}_size_bytes IS NULL) "
            f"AND ({prefix}_storage_key IS NULL) = ({prefix}_sha256 IS NULL)",
            name=f"{prefix}_all_or_none",
        ),
        CheckConstraint(
            f"{prefix}_storage_key IS NULL "
            f"OR (length({prefix}_storage_key) BETWEEN 1 AND 500 AND {prefix}_storage_key !~ '^/')",
            name=f"{prefix}_key_length",
        ),
        CheckConstraint(
            f"{prefix}_content_type IS NULL OR "
            + in_list(f"{prefix}_content_type", IMAGE_CONTENT_TYPES),
            name=f"{prefix}_content_type_image",
        ),
        CheckConstraint(
            f"{prefix}_size_bytes IS NULL OR {prefix}_size_bytes BETWEEN 1 AND 5242880",
            name=f"{prefix}_size_range",
        ),
        CheckConstraint(
            f"{prefix}_sha256 IS NULL OR {prefix}_sha256 ~ '{HEX64}'",
            name=f"{prefix}_sha256_format",
        ),
        CheckConstraint(f"{prefix}_version >= 0", name=f"{prefix}_version_range"),
    )


class Campaign(ScopeMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        *scope_constraints("campaigns"),
        user_fk("campaigns", "created_by_user_id"),
        UniqueConstraint(
            "id", "organization_id", "school_id", name="uq_campaigns_id_organization_id_school_id"
        ),
        CheckConstraint(in_list("status", CAMPAIGN_STATUSES), name="status_valid"),
        CheckConstraint("length(btrim(title)) BETWEEN 1 AND 120", name="title_length"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000", name="description_length"
        ),
        CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on", name="dates_in_order"
        ),
        CheckConstraint("(status = 'ENDED') = (ended_at IS NOT NULL)", name="ended_iff_status"),
        *_image_checks("cover"),
        Index("ix_campaigns_school_id_status", "school_id", "status", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'DRAFT'"))
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The family must say the student and the class when it orders (0014).
    ask_student_class: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    cover_storage_key: Mapped[str | None] = mapped_column(Text)
    cover_content_type: Mapped[str | None] = mapped_column(Text)
    cover_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    cover_sha256: Mapped[str | None] = mapped_column(Text)
    cover_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignItem(ScopeMixin, Base):
    """A product of a campaign. Never deleted: one that was sold is switched off."""

    __tablename__ = "campaign_items"
    __table_args__ = (
        *scope_constraints("campaign_items"),
        ForeignKeyConstraint(
            ["campaign_id", "organization_id", "school_id"],
            ["campaigns.id", "campaigns.organization_id", "campaigns.school_id"],
            name="fk_campaign_items_campaign_id_campaigns",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id",
            "campaign_id",
            "organization_id",
            "school_id",
            name="uq_campaign_items_id_campaign_id_organization_id_school_id",
        ),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 500", name="description_length"
        ),
        CheckConstraint("price_cents BETWEEN 100 AND 1000000", name="price_range"),
        CheckConstraint(
            "max_per_order IS NULL OR max_per_order BETWEEN 1 AND 99", name="max_per_order_range"
        ),
        CheckConstraint("position BETWEEN 0 AND 999", name="position_range"),
        CheckConstraint(
            "unit_cost_cents IS NULL OR unit_cost_cents BETWEEN 0 AND 1000000",
            name="unit_cost_range",
        ),
        *_image_checks("image"),
        Index("ix_campaign_items_campaign_id", "campaign_id", "position"),
        Index("ix_campaign_items_school_id", "school_id"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(BigInteger)
    # What one unit costs the APM (0014): a management metric, not a ledger entry.
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_per_order: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    image_storage_key: Mapped[str | None] = mapped_column(Text)
    image_content_type: Mapped[str | None] = mapped_column(Text)
    image_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    image_sha256: Mapped[str | None] = mapped_column(Text)
    image_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContributionItem(ScopeMixin, Base):
    """What an order bought: a COPY of the name and of the price, written once and never changed."""

    __tablename__ = "contribution_items"
    __table_args__ = (
        *scope_constraints("contribution_items"),
        ForeignKeyConstraint(
            ["transaction_id", "organization_id", "school_id"],
            [
                "contributions.transaction_id",
                "contributions.organization_id",
                "contributions.school_id",
            ],
            name="fk_contribution_items_transaction_id_contributions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["campaign_item_id", "campaign_id", "organization_id", "school_id"],
            [
                "campaign_items.id",
                "campaign_items.campaign_id",
                "campaign_items.organization_id",
                "campaign_items.school_id",
            ],
            name="fk_contribution_items_campaign_item_id_campaign_items",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "school_id",
            "transaction_id",
            "campaign_item_id",
            name="uq_contribution_items_school_id_transaction_id_campaign_item_id",
        ),
        CheckConstraint("length(btrim(item_name)) BETWEEN 1 AND 120", name="item_name_length"),
        CheckConstraint("unit_price_cents BETWEEN 100 AND 1000000", name="unit_price_range"),
        CheckConstraint("quantity BETWEEN 1 AND 99", name="quantity_range"),
        CheckConstraint(
            "unit_cost_cents IS NULL OR unit_cost_cents BETWEEN 0 AND 1000000",
            name="unit_cost_range",
        ),
        Index("ix_contribution_items_transaction_id", "transaction_id"),
        Index("ix_contribution_items_campaign_item_id", "campaign_item_id"),
        Index("ix_contribution_items_school_id", "school_id"),
    )

    id: Mapped[uuid.UUID] = fin_pk()
    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    campaign_item_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    item_name: Mapped[str] = mapped_column(Text)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    # The copy of the cost of the product at the purchase, filled by a trigger (0014).
    unit_cost_cents: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignDelivery(ScopeMixin, Base):
    """The delivery state of an order of a campaign (0014): a row appears when the management first
    marks the order, and it can be switched back. The database accepts DELIVERED only for a PAID
    order of a campaign."""

    __tablename__ = "campaign_deliveries"
    __table_args__ = (
        *scope_constraints("campaign_deliveries"),
        ForeignKeyConstraint(
            ["transaction_id", "organization_id", "school_id"],
            [
                "contributions.transaction_id",
                "contributions.organization_id",
                "contributions.school_id",
            ],
            name="fk_campaign_deliveries_transaction_id_contributions",
            ondelete="RESTRICT",
        ),
        user_fk("campaign_deliveries", "changed_by_user_id"),
        CheckConstraint(in_list("status", ("PENDING", "DELIVERED")), name="status_valid"),
        Index("ix_campaign_deliveries_school_id", "school_id"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    school_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(Text, server_default=text("'DELIVERED'"))
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContributionFee(ScopeMixin, Base):
    """The fee the gateway kept from a PAID contribution (0016): written once, with the gross
    amount of the ledger row, and never changed. `net_cents` is computed by the database."""

    __tablename__ = "contribution_fees"
    __table_args__ = (
        *scope_constraints("contribution_fees"),
        ForeignKeyConstraint(
            ["transaction_id", "organization_id", "school_id"],
            [
                "contributions.transaction_id",
                "contributions.organization_id",
                "contributions.school_id",
            ],
            name="fk_contribution_fees_transaction_id_contributions",
            ondelete="RESTRICT",
        ),
        CheckConstraint("gross_cents > 0", name="gross_positive"),
        CheckConstraint(
            "gateway_fee_cents >= 0 AND gateway_fee_cents <= gross_cents", name="fee_range"
        ),
        CheckConstraint(in_list("fee_payer", ("SCHOOL", "PAYER")), name="fee_payer_valid"),
        Index("ix_contribution_fees_school_id", "school_id"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    school_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    gross_cents: Mapped[int] = mapped_column(BigInteger)
    gateway_fee_cents: Mapped[int] = mapped_column(BigInteger)
    fee_payer: Mapped[str] = mapped_column(Text, server_default=text("'SCHOOL'"))
    net_cents: Mapped[int] = mapped_column(
        BigInteger,
        Computed(
            "CASE fee_payer WHEN 'SCHOOL' THEN gross_cents - gateway_fee_cents "
            "ELSE gross_cents END",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
