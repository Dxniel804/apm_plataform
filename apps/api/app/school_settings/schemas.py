"""The settings of a school the management edits, and its public link (snake_case, cents)."""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.schemas.auth import Strict, _storable

Cents = Annotated[int, Field(ge=100, le=1_000_000_000)]
FreeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(_storable),
]


class SettingsOut(BaseModel):
    suggested_amounts_cents: list[int]
    allow_custom_amount: bool
    min_contribution_cents: int
    max_contribution_cents: int
    # A sentence the family reads next to the free amount.
    free_amount_text: str | None
    # What the school hopes to collect in a month and how many contributions it expects (null:
    # not set).
    monthly_goal_cents: int | None
    expected_contributions: int | None


class SettingsPatch(Strict):
    """Only what is sent changes; `null` clears the three optional fields (text and goals)."""

    suggested_amounts_cents: Annotated[list[Cents], Field(min_length=1, max_length=6)] | None = None
    allow_custom_amount: bool | None = None
    free_amount_text: FreeText | None = None
    monthly_goal_cents: Annotated[int, Field(ge=100, le=100_000_000_000)] | None = None
    expected_contributions: Annotated[int, Field(ge=1, le=100_000)] | None = None


class PublicLinkOut(BaseModel):
    school_id: uuid.UUID
    school_name: str
    slug: str
    # The address the families open (and the QR code carries): PUBLIC_BASE_URL + /escola/{slug}.
    url: str
