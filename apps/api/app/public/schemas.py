"""The JSON of the public contribution flow (ADR-017, ADR-018). Money in cents, snake_case."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Presence = Literal["REQUIRED", "OPTIONAL", "HIDDEN"]


class PublicSchoolOut(BaseModel):
    """What the page of a school needs. The ids of the school and of its organization stay on the
    server."""

    slug: str
    name: str
    apm_name: str
    accent_color: str
    accent_contrast_color: str
    suggested_amounts_cents: list[int]
    allow_custom_amount: bool
    min_amount_cents: int
    max_amount_cents: int
    identification: dict[str, Presence]


class Identification(BaseModel):
    """Who is giving: what the family typed. Only the fields the school asks for are stored."""

    model_config = ConfigDict(extra="forbid")

    guardian_name: str | None = Field(default=None, max_length=120)
    student_name: str | None = Field(default=None, max_length=120)
    class_name: str | None = Field(default=None, max_length=120)
    contributor_email: str | None = Field(default=None, max_length=254)
    contributor_phone: str | None = Field(default=None, max_length=30)


class ContributionIn(Identification):
    """What the family sends. The server revalidates everything against the settings of the school
    and stores only the fields that school asks for."""

    amount_cents: int = Field(gt=0, le=1_000_000_000)


class ChargeOut(BaseModel):
    status: Literal["PENDING", "PAID", "REVIEW_REQUIRED", "EXPIRED", "CANCELLED"]
    amount_cents: int
    emv_payload: str | None
    expires_at: datetime


class ContributionStateOut(BaseModel):
    status: str
    amount_cents: int
    charge: ChargeOut | None


class ContributionCreatedOut(ContributionStateOut):
    """The answer of the POST: the state, plus the opaque token that opens it again (the same key
    always yields the same token). It is a secret of the family: keep it out of logs and URLs shared
    with anybody."""

    token: str


class ReceiptItemOut(BaseModel):
    """One line of what an order bought, as it was bought (the name and the price of that day)."""

    name: str
    unit_price_cents: int
    quantity: int


class ReceiptOut(BaseModel):
    status: Literal["PAID"]
    reference_code: str
    amount_cents: int
    paid_at: datetime
    school_name: str
    method: str
    # Only for the order of a campaign: its title and what it bought (the sum is `amount_cents`).
    campaign_title: str | None = None
    items: list[ReceiptItemOut] = []


# --- the campaigns on sale (migration 0013) ------------------------------------------------------


class PublicItemOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price_cents: int
    max_per_order: int | None
    has_image: bool
    image_version: int


class PublicCampaignSummary(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    ends_on: date | None
    has_cover: bool
    cover_version: int
    items_count: int
    # The order must say the student and the class (so the management knows to whom to deliver).
    ask_student_class: bool


class PublicCampaignOut(PublicCampaignSummary):
    items: list[PublicItemOut]


class PublicCampaignList(BaseModel):
    campaigns: list[PublicCampaignSummary]


class OrderLineIn(BaseModel):
    """A product and how many. The price is NEVER here: the server reads it."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    quantity: int = Field(ge=1, le=99)


class OrderIn(Identification):
    """The cart of a family: the lines and who is giving. The total is computed by the server."""

    lines: list[OrderLineIn] = Field(min_length=1, max_length=20)
