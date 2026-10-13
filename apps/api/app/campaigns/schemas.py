"""The HTTP contract of the campaigns the management writes: snake_case, money in cents, ISO dates.
The states of the database are sent as they are (the site translates them)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.schemas.auth import Strict, _storable

CampaignStatus = Literal["DRAFT", "ACTIVE", "ENDED"]

# Stripped text of a length, and storable (no NUL byte, no lone surrogate).
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_storable),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    AfterValidator(_storable),
]
ItemName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_storable),
]
ItemText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(_storable),
]
# R$ 1,00 to R$ 10.000,00 per unit (the database refuses anything else).
PriceCents = Annotated[int, Field(ge=100, le=1_000_000)]
MaxPerOrder = Annotated[int, Field(ge=1, le=99)]
Position = Annotated[int, Field(ge=0, le=999)]


class CampaignCreate(Strict):
    title: Title
    description: LongText | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None


class CampaignPatch(Strict):
    """Only what is sent changes; `null` clears an optional field (the dates, the text)."""

    title: Title | None = None
    description: LongText | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None


class ItemCreate(Strict):
    name: ItemName
    description: ItemText | None = None
    price_cents: PriceCents
    max_per_order: MaxPerOrder | None = None
    position: Position = 0


class ItemPatch(Strict):
    """Only what is sent changes; `null` clears the text or the limit per order."""

    name: ItemName | None = None
    description: ItemText | None = None
    price_cents: PriceCents | None = None
    max_per_order: MaxPerOrder | None = None
    position: Position | None = None
    is_active: bool | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price_cents: int
    max_per_order: int | None
    position: int
    is_active: bool
    has_image: bool
    image_version: int


class CampaignSummary(BaseModel):
    id: uuid.UUID
    title: str
    status: CampaignStatus
    starts_on: dt.date | None
    ends_on: dt.date | None
    has_cover: bool
    items_count: int
    active_items_count: int
    # What the orders already paid brought in: how many and how much (the money is in the ledger).
    paid_orders_count: int
    paid_cents: int
    created_at: dt.datetime
    updated_at: dt.datetime


class CampaignDetail(CampaignSummary):
    description: str | None
    cover_version: int
    items: list[ItemOut]


class CampaignList(BaseModel):
    items: list[CampaignSummary]
