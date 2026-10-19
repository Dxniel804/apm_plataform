# ruff: noqa: E501  (long lines)
"""The contract of the tax guides (migration 0029): snake_case, money in cents, a rate in basis points."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from app.schemas.auth import Strict, _storable

TaxKind = Literal["IRRF", "INSS", "ISS", "OTHER"]
AppliesTo = Literal["PF", "PJ", "BOTH"]
Roll = Literal["PREVIOUS", "NEXT"]
Provider = Literal["PF", "PJ"]


Label = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_storable),
]
Howto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(_storable),
]
Source = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_storable),
]
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_storable),
]
Note = Annotated[str, StringConstraints(max_length=300), AfterValidator(_storable)]


class RuleIn(Strict):
    rule_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,39}$")
    label: Label
    tax_kind: TaxKind
    applies_to: AppliesTo
    rate_bps: int = Field(ge=1, le=10000)
    base_cap_cents: int | None = Field(default=None, ge=1, le=100_000_000_000)
    min_total_cents: int = Field(default=1000, ge=0, le=100_000_000)
    darf_code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    howto: Howto | None = None
    due_day: int = Field(ge=1, le=31)
    due_roll: Roll
    source_note: Source | None = None
    # The accountant confirmed this rule. Never assumed: an unticked rule counts as NOT validated.
    validated: bool = False

    @model_validator(mode="after")
    def _where_to_pay(self) -> "RuleIn":
        if self.darf_code is None and self.howto is None:
            raise ValueError("say the code of the guide or how it is paid")
        return self


class RuleOut(BaseModel):
    id: uuid.UUID
    rule_key: str
    label: str
    tax_kind: TaxKind
    applies_to: AppliesTo
    rate_bps: int
    base_cap_cents: int | None
    min_total_cents: int
    darf_code: str | None
    howto: str | None
    due_day: int
    due_roll: Roll
    source_note: str | None
    validated: bool
    validated_at: dt.datetime | None


class SuggestionOut(BaseModel):
    """A starting point to copy into a rule. NOT validated and never applied by itself: the figures
    come from non-official sources and the law changes, so the accountant has to confirm each one."""

    rule_key: str
    label: str
    tax_kind: TaxKind
    applies_to: AppliesTo
    rate_bps: int | None
    base_cap_cents: int | None
    darf_code: str | None
    howto: str | None
    warning: str


class RulesOut(BaseModel):
    rules: list[RuleOut]
    suggestions: list[SuggestionOut]


class RetentionIn(Strict):
    rule_id: uuid.UUID
    provider_kind: Provider
    provider_name: Name
    competence: str = Field(pattern=r"^(19|20|21)\d{2}-(0[1-9]|1[0-2])$")
    gross_cents: int = Field(ge=1, le=100_000_000_000)
    note: Note | None = None


class PreviewOut(BaseModel):
    base_cents: int
    retained_cents: int
    net_cents: int
    rate_bps: int


class RetentionOut(BaseModel):
    id: uuid.UUID
    rule_key: str
    rule_label: str
    provider_kind: Provider
    provider_name: str
    competence: str
    gross_cents: int
    base_cents: int
    retained_cents: int
    net_cents: int
    rate_bps: int
    note: str | None
    voided: bool
    validated: bool


class GuideOut(BaseModel):
    """What to type in the site of the Receita (or where to pay), for one tax and one month."""

    rule_key: str
    label: str
    tax_kind: TaxKind
    darf_code: str | None
    howto: str | None
    competence: str
    due_date: dt.date
    total_cents: int
    count: int
    min_total_cents: int
    below_minimum: bool
    validated: bool
    mixed_versions: bool
    site_url: str | None


class MonthOut(BaseModel):
    period: str
    retentions: list[RetentionOut]
    guides: list[GuideOut]
