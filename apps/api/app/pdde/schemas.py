# ruff: noqa: E501  (long lines)
"""The contract of the PDDE accountability layer (migration 0028): snake_case, money in cents."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from app.pdde import nfe, tax_id
from app.schemas.auth import Strict, _storable

Program = Literal["BASICO", "EQUIDADE", "QUALIDADE", "CONECTADO", "OUTRO"]
Economic = Literal["CUSTEIO", "CAPITAL"]
Kind = Literal[
    "TRANSFER", "YIELD", "EXPENSE", "RETURN_TO_FNDE", "TAX_TO_EEX", "REFUND", "INELIGIBLE"
]
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


Specification = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_storable),
]


class ClassificationIn(Strict):
    kind: Kind
    program: Program | None = None
    program_label: Label | None = None  # the name of the program when `OUTRO`
    economic_category: Economic | None = None
    object: ObjectText | None = None
    note: Note | None = None
    payment_number: Number | None = None  # the check or the bank order that paid it (field 26)

    @model_validator(mode="after")
    def _shape(self) -> "ClassificationIn":
        if self.kind in ("TRANSFER", "YIELD", "EXPENSE", "RETURN_TO_FNDE") and self.program is None:
            raise ValueError("program is required")
        if self.kind in ("YIELD", "RETURN_TO_FNDE") and self.economic_category is None:
            raise ValueError("a yield or a return needs custeio or capital")
        if self.kind in ("YIELD", "RETURN_TO_FNDE") and self.object is not None:
            raise ValueError("a yield or a return has no object")
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
    vendor_tax_id: str | None = Field(default=None, max_length=24)  # CNPJ or CPF of who was paid
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)  # a good of capital
    specification: Specification | None = None  # what the good is (the Relação de bens)

    @model_validator(mode="after")
    def _shape(self) -> "DocumentIn":
        if self.vendor_tax_id is not None:
            digits = tax_id.normalize(self.vendor_tax_id)
            if not tax_id.is_valid(digits):
                raise ValueError("the CNPJ or the CPF is not valid")
            self.vendor_tax_id = digits
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
    vendor_tax_id: str | None = None
    quantity: int | None = None
    specification: str | None = None


class ClassificationOut(BaseModel):
    kind: Kind
    program: Program | None
    program_label: str | None
    economic_category: Economic | None
    object: str | None
    note: str | None
    payment_number: str | None = None


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


class BankBalance(BaseModel):
    """What the bank says a PDDE account holds, from its latest statement up to the end of the month."""

    account_id: uuid.UUID
    account_nickname: str
    balance_cents: int | None  # None: no statement with a balance was imported yet
    as_of: dt.date | None  # the last day of that statement


class MonthOut(BaseModel):
    period: str
    accounts: list[AccountOut]
    bank_balances: list[BankBalance]
    lines: list[LineOut]
    pending_count: int
    alerts: list[AlertOut]


class ProgramBalance(BaseModel):
    program: Program
    program_label: str | None
    received_cents: int
    yield_cents: int = 0
    returned_cents: int = 0
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


# --- the entity and the carry-over printed on the official forms -------------------------------------

UFS = frozenset(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)


LegalName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_storable),
]
Address = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_storable),
]
City = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_storable),
]


class EntityIn(Strict):
    legal_name: LegalName  # as the card of the CNPJ writes it
    cnpj: str = Field(max_length=24)
    address: Address
    city: City
    state: str = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _shape(self) -> "EntityIn":
        digits = tax_id.normalize(self.cnpj)
        if not tax_id.is_valid_cnpj(digits):
            raise ValueError("the CNPJ is not valid")
        self.cnpj = digits
        self.state = self.state.upper()
        if self.state not in UFS:
            raise ValueError("unknown state")
        return self


class EntityOut(BaseModel):
    legal_name: str
    cnpj: str
    address: str
    city: str
    state: str


class CarryoverIn(Strict):
    year: int = Field(ge=2000, le=2100)
    program: Program
    program_label: Label | None = None
    custeio_cents: int = Field(ge=0, le=100_000_000_000)
    capital_cents: int = Field(ge=0, le=100_000_000_000)

    @model_validator(mode="after")
    def _shape(self) -> "CarryoverIn":
        if (self.program == "OUTRO") != (self.program_label is not None):
            raise ValueError("the name of the program goes with OUTRO and only with it")
        return self


class CarryoverOut(BaseModel):
    program: Program
    program_label: str | None
    custeio_cents: int
    capital_cents: int
