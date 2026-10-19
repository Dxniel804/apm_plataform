"""The contract of the PDDE accountability layer (migration 0028): snake_case, money in cents."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from app.pdde import nfe
from app.schemas.auth import Strict, _storable

Program = Literal["BASICO", "EQUIDADE", "QUALIDADE", "CONECTADO", "OUTRO"]
Economic = Literal["CUSTEIO", "CAPITAL"]
Kind = Literal["TRANSFER", "EXPENSE", "TAX_TO_EEX", "REFUND", "INELIGIBLE"]
DocKind = Literal["NFE", "INVOICE", "RECEIPT", "OTHER"]
Status = Literal["PENDING", "PARTIAL", "DONE"]


Label = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(_storable),
]
ObjectText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_storable),
]
Vendor = ObjectText
Number = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(_storable),
]
Note = Annotated[str, StringConstraints(max_length=300), AfterValidator(_storable)]


class ClassificationIn(Strict):
    kind: Kind
    program: Program | None = None
    program_label: Label | None = None  # the name of the program when `OUTRO`
    economic_category: Economic | None = None
    object: ObjectText | None = None
    note: Note | None = None

    @model_validator(mode="after")
    def _shape(self) -> "ClassificationIn":
        if self.kind in ("TRANSFER", "EXPENSE") and self.program is None:
            raise ValueError("program is required")
        if self.kind == "EXPENSE" and (self.economic_category is None or self.object is None):
            raise ValueError("an expense needs custeio or capital and its object")
        if self.kind == "TRANSFER" and self.object is not None:
            raise ValueError("a repasse has no object")
        if (self.program == "OUTRO") != (self.program_label is not None):
            raise ValueError("the name of the program goes with OUTRO and only with it")
        return self


class DocumentIn(Strict):
    doc_kind: DocKind
    access_key: str | None = Field(default=None, max_length=70)
    doc_number: Number | None = None
    issued_on: dt.date
    vendor: Vendor
    amount_cents: int = Field(gt=0, le=100_000_000_000)
    stamped: bool = False  # "Pagos com recursos do PDDE ..." is on the document

    @model_validator(mode="after")
    def _shape(self) -> "DocumentIn":
        if self.doc_kind == "NFE":
            key = nfe.normalize(self.access_key or "")
            if not nfe.is_valid_key(key):
                raise ValueError("the access key of the NF-e is not valid")
            self.access_key = key
        elif self.access_key:
            raise ValueError("only a NF-e has an access key")
        return self


class DocumentOut(BaseModel):
    id: uuid.UUID
    doc_kind: DocKind
    access_key: str | None
    doc_number: str | None
    issued_on: dt.date
    vendor: str
    amount_cents: int
    stamped: bool
    voided: bool


class ClassificationOut(BaseModel):
    kind: Kind
    program: Program | None
    program_label: str | None
    economic_category: Economic | None
    object: str | None
    note: str | None


class LineOut(BaseModel):
    line_id: uuid.UUID
    account_id: uuid.UUID
    account_nickname: str
    posted_on: dt.date
    amount_cents: int
    memo: str
    looks_like_fee: bool
    classification: ClassificationOut | None
    documents: list[DocumentOut]
    documented_cents: int
    status: Status


class AccountOut(BaseModel):
    id: uuid.UUID
    nickname: str
    bank_name: str
    account_last4: str | None


class AlertOut(BaseModel):
    """`code` is stable (the site writes the sentence); the numbers are what it needs to say."""

    code: Literal[
        "fee_on_pdde_account",
        "pending_lines",
        "spent_over_received",
        "year_end_reconciliation",
        "deadline",
        "deadline_passed",
    ]
    count: int = 0
    cents: int = 0
    program: Program | None = None
    economic_category: Economic | None = None
    date: dt.date | None = None


class MonthOut(BaseModel):
    period: str
    accounts: list[AccountOut]
    lines: list[LineOut]
    pending_count: int
    alerts: list[AlertOut]


class ProgramBalance(BaseModel):
    program: Program
    program_label: str | None
    received_cents: int
    spent_custeio_cents: int
    spent_capital_cents: int
    balance_cents: int


class YearEndBalance(BaseModel):
    account_id: uuid.UUID
    account_nickname: str
    balance_cents: (
        int | None
    )  # the bank's closing balance of 31/12, when a statement of December was imported


class YearOut(BaseModel):
    year: int
    accounts: list[AccountOut]
    programs: list[ProgramBalance]
    pending_count: int
    year_end: list[YearEndBalance]
    alerts: list[AlertOut]
