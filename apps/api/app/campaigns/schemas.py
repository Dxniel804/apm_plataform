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
# What one unit costs the APM: R$ 0,00 to R$ 10.000,00 (a gift can cost nothing).
CostCents = Annotated[int, Field(ge=0, le=1_000_000)]
MaxPerOrder = Annotated[int, Field(ge=1, le=99)]
Position = Annotated[int, Field(ge=0, le=999)]


class CampaignCreate(Strict):
    title: Title
    description: LongText | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    # The family must say the student and the class (so the management knows to whom to deliver).
    ask_student_class: bool = True


class CampaignPatch(Strict):
    """Only what is sent changes; `null` clears an optional field (the dates, the text)."""

    title: Title | None = None
    description: LongText | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    ask_student_class: bool | None = None


class ItemCreate(Strict):
    name: ItemName
    description: ItemText | None = None
    price_cents: PriceCents
    unit_cost_cents: CostCents | None = None
    max_per_order: MaxPerOrder | None = None
    position: Position = 0


class ItemPatch(Strict):
    """Only what is sent changes; `null` clears the text or the limit per order."""

    name: ItemName | None = None
    description: ItemText | None = None
    price_cents: PriceCents | None = None
    unit_cost_cents: CostCents | None = None
    max_per_order: MaxPerOrder | None = None
    position: Position | None = None
    is_active: bool | None = None


class ItemOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price_cents: int
    unit_cost_cents: int | None
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
    ask_student_class: bool
    items: list[ItemOut]


class CampaignList(BaseModel):
    items: list[CampaignSummary]


# --- the dashboard of one campaign, its orders and their delivery (0014) ----------------------

# What the panel shows for the payment of an order: waiting (the Pix is still open, or in review),
# approved, or cancelled (cancelled, expired).
PaymentStatus = Literal["PENDING", "PAID", "CANCELLED"]
DeliveryStatus = Literal["PENDING", "DELIVERED"]


class SoldItem(BaseModel):
    """One product of the campaign and what its PAID orders took: units, revenue and, when the cost
    was known at every purchase, the cost."""

    item_id: uuid.UUID
    name: str
    units_sold: int
    revenue_cents: int
    cost_cents: int | None
    cost_known: bool


class CampaignDashboard(BaseModel):
    campaign_id: uuid.UUID
    title: str
    status: CampaignStatus
    paid_orders_count: int
    pending_orders_count: int
    cancelled_orders_count: int
    # Collected: what the PAID orders brought in (the same figure the ledger holds).
    collected_cents: int
    units_sold: int
    # The cost is a management metric, NOT a ledger entry (the real outflow is the expense).
    cost_cents: int
    # False when some unit sold has no cost: then there is no profit to show.
    cost_complete: bool
    profit_cents: int | None
    delivered_orders_count: int
    to_deliver_orders_count: int
    items: list[SoldItem]


class OrderLine(BaseModel):
    item_name: str
    quantity: int
    unit_price_cents: int


class OrderOut(BaseModel):
    order_id: uuid.UUID
    reference_code: int
    created_at: dt.datetime
    guardian_name: str | None
    student_name: str | None
    class_name: str | None
    amount_cents: int
    payment_status: PaymentStatus
    # Only an order that was paid has a delivery state.
    delivery_status: DeliveryStatus | None
    delivery_changed_at: dt.datetime | None
    lines: list[OrderLine]


class BuyerLine(BaseModel):
    item_name: str
    quantity: int


class BuyerOut(BaseModel):
    """What one guardian bought for one student in the campaign (the paid orders only): the same
    person with the name written in another way is the same buyer."""

    guardian_name: str | None
    student_name: str | None
    class_name: str | None
    orders: int
    units: int
    amount_cents: int
    lines: list[BuyerLine]


class BuyerList(BaseModel):
    items: list[BuyerOut]
    # False when the campaign has more paid orders than the ones counted (the most recent 5000).
    complete: bool


class OrderList(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int


class DeliveryChange(Strict):
    order_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=100)]
    delivered: bool


class DeliveryResult(BaseModel):
    changed: int
    unchanged: int
    # Not paid, not of this campaign, or unknown: all the same answer.
    skipped: int
