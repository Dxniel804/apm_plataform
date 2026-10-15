"""The contract of the bank reconciliation (migration 0017): snake_case, money in cents."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints

from app.schemas.auth import Strict, _storable

Purpose = Literal["GENERAL", "PDDE"]
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(_storable),
]
Last4 = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,4}$")]


class AccountCreate(Strict):
    nickname: Name
    bank_name: Name
    # Only the last digits: the full number of an account is never stored.
    account_last4: Last4 | None = None
    purpose: Purpose = "GENERAL"


class AccountPatch(Strict):
    nickname: Name | None = None
    bank_name: Name | None = None
    account_last4: Last4 | None = None
    purpose: Purpose | None = None
    is_active: bool | None = None


class AccountOut(BaseModel):
    id: uuid.UUID
    nickname: str
    bank_name: str
    account_last4: str | None
    purpose: Purpose
    is_active: bool


class ImportOut(BaseModel):
    id: uuid.UUID
    bank_account_id: uuid.UUID
    period_start: dt.date
    period_end: dt.date
    line_count: int
    new_line_count: int
    closing_balance_cents: int | None
    created_at: dt.datetime


class ImportList(BaseModel):
    items: list[ImportOut]


class BankLineOut(BaseModel):
    line_id: uuid.UUID
    posted_on: dt.date
    amount_cents: int
    memo: str
    end_to_end_id: str | None
    looks_like_fee: bool


class LedgerEntryOut(BaseModel):
    transaction_id: uuid.UUID
    reference_code: int
    kind: str
    day: dt.date
    amount_cents: int  # signed like the bank: in is positive
    net_cents: int | None  # what the bank receives when a gateway kept a fee


class MatchedOut(BaseModel):
    line: BankLineOut
    entry: LedgerEntryOut


class DivergenceOut(BaseModel):
    line: BankLineOut
    candidates: list[LedgerEntryOut]
    reason: Literal["ambiguous", "amount_differs"]


class ReconciliationOut(BaseModel):
    """The four lists of the screen. Nothing is written: the ledger and the bank, side by side."""

    statement: ImportOut
    matched: list[MatchedOut]
    missing_in_system: list[BankLineOut]
    missing_in_bank: list[LedgerEntryOut]
    divergences: list[DivergenceOut]
