"""The settings of a school the management edits, and its public link (snake_case, cents)."""

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator

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


SchoolName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=120),
    AfterValidator(_storable),
]


class IdentityOut(BaseModel):
    """The name and the address of the school, and what is left of the changes of the address."""

    school_id: uuid.UUID
    name: str
    slug: str
    # The address the families open: PUBLIC_BASE_URL + /escola/{slug}.
    url: str
    slug_changes: int
    # Two changes are free; from the third, 15 days after the previous one.
    free_changes_left: int
    # Null: the address may be changed now. Otherwise, the moment it may be changed again.
    slug_locked_until: datetime | None
    # False while the school has no active receiving account: the public page opens only with one.
    link_active: bool
    # Every address the school had: they keep opening this school (and never go to another one).
    previous_slugs: list[str]


class IdentityPatch(Strict):
    """Only what is sent changes."""

    name: SchoolName | None = None
    slug: str | None = Field(default=None, min_length=3, max_length=40)

    @field_validator("slug")
    @classmethod
    def _normalise(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", value):
            raise ValueError("use only lower-case letters, numbers and single hyphens")
        return value
