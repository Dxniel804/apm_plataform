# ruff: noqa: E501  (openapi blocks)
"""The balancete of the month (the accountant's sheet): the numbers, the PDF, and the balances the
ledger does not know (what the school had when it started; cash and invested at the end of a month)."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import DBAPIError

from app.auth.deps import Principal, require
from app.auth.permissions import Permission
from app.core.errors import ProblemError
from app.reports import balancete, queries
from app.reports.closing_report import ReportMismatch
from app.reports.routes import PDF_RESPONSE, READ, PeriodQuery, pdf_response
from app.statement.deps import (
    InSchool,
    TenantDb,
    month_of,
    not_found,
    permission_extra,
    require_any,
    responses_of,
)
from app.statement.periods import month_bounds, period_of
from app.statement.queries import fetch_summary

router = APIRouter(prefix="/api/v1/schools/{school_id}", tags=["balancete"])

CENTS = Field(ge=0, le=100_000_000_000)


class LineOut(BaseModel):
    name: str
    cents: int


class PlaceOut(BaseModel):
    bank_cents: int
    cash_cents: int
    investment_cents: int
    total_cents: int


class BalanceteOut(BaseModel):
    period: str
    opening: PlaceOut
    revenue: list[LineOut]
    total_revenue_cents: int
    capital: list[LineOut]
    total_capital_cents: int
    expenses: list[LineOut]
    total_expenses_cents: int
    balance_of_month_cents: int
    closing: PlaceOut
    closing_typed: bool = Field(description="False: cash and invested were carried from before.")
    has_opening: bool = Field(description="Whether the starting balance of the school was typed.")


class BalanceIn(BaseModel):
    """What the treasurer types. `OPENING`: the day the school started to use the system (bank, cash
    and invested). `MONTH`: at the end of `period`, how much is in cash and how much is invested."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["OPENING", "MONTH"]
    period: str | None = Field(default=None, pattern=r"^(19|20|21)\d{2}-(0[1-9]|1[0-2])$")
    bank_cents: int | None = Field(default=None, ge=-100_000_000_000, le=100_000_000_000)
    cash_cents: int = CENTS
    investment_cents: int = CENTS

    @model_validator(mode="after")
    def _shape(self) -> "BalanceIn":
        if self.kind == "OPENING" and (self.period is not None or self.bank_cents is None):
            raise ValueError("the starting balance has no month and needs the bank")
        if self.kind == "MONTH" and (self.period is None or self.bank_cents is not None):
            raise ValueError("a month needs its period and does not take the bank")
        return self


class Sheet:
    """The month's sheet and where it came from."""

    def __init__(self, chosen: str, sheet: balancete.Balancete, has_opening: bool) -> None:
        self.chosen = chosen
        self.sheet = sheet
        self.has_opening = has_opening


def _place(place: balancete.Place) -> PlaceOut:
    return PlaceOut(
        bank_cents=place.bank_cents,
        cash_cents=place.cash_cents,
        investment_cents=place.investment_cents,
        total_cents=place.total_cents,
    )


def _sheet(db: TenantDb, scope: InSchool, period: str | None) -> Sheet:
    """The sheet of the month, read again once if the ledger moved while it was being read."""
    chosen, start, end = month_of(db, scope, period)
    organization_name, school_name = queries.names(db, scope.school_id)
    previous_start = (start - timedelta(days=1)).replace(day=1)
    generated_at = datetime.now(UTC)
    for attempt in (1, 2):
        summary = fetch_summary(db, scope.school_id, start, end)
        if summary is None:
            raise not_found()
        opening = queries.latest_balance(db, scope.school_id, "OPENING", None)
        try:
            sheet = balancete.build_balancete(
                entries=queries.period_entries(db, scope.school_id, start, end),
                summary=summary,
                category_names=queries.category_names(db, scope.school_id),
                balances=balancete.Balances(
                    opening=opening,
                    previous=queries.latest_balance(db, scope.school_id, "MONTH", previous_start),
                    current=queries.latest_balance(db, scope.school_id, "MONTH", start),
                ),
                organization_name=organization_name,
                school_name=school_name,
                period_start=start,
                period_end=end,
                generated_at=generated_at,
            )
            return Sheet(chosen, sheet, opening is not None)
        except ReportMismatch:
            if attempt == 2:
                raise ProblemError(
                    409, "report_mismatch", "The ledger changed while the report was being made"
                ) from None
    raise AssertionError("unreachable")  # pragma: no cover


@router.get(
    "/balancete",
    operation_id="balancete_get",
    summary="The balancete of a month, in the shape of the accountant's sheet",
    response_model=BalanceteOut,
    responses=responses_of(401, 403, 404, 409, 422),
    openapi_extra=permission_extra(*READ),
)
def get_balancete(
    principal: Annotated[Principal, Depends(require_any(*READ))],
    scope: InSchool,
    db: TenantDb,
    period: PeriodQuery = None,
) -> BalanceteOut:
    """Every number is the ledger's, checked against `statement_summary` (409 `report_mismatch` if
    it moved twice in a row while being read). No personal data: only purposes and totals."""
    found = _sheet(db, scope, period)
    s = found.sheet
    return BalanceteOut(
        period=found.chosen,
        opening=_place(s.opening),
        revenue=[LineOut(name=x.name, cents=x.cents) for x in s.revenue],
        total_revenue_cents=s.total_revenue,
        capital=[LineOut(name=x.name, cents=x.cents) for x in s.capital],
        total_capital_cents=s.total_capital,
        expenses=[LineOut(name=x.name, cents=x.cents) for x in s.expenses],
        total_expenses_cents=s.total_expenses,
        balance_of_month_cents=s.balance_of_month,
        closing=_place(s.closing),
        closing_typed=s.closing_typed,
        has_opening=found.has_opening,
    )


@router.get(
    "/balancete.pdf",
    operation_id="balancete_pdf",
    summary="The balancete of a month as a PDF, with the lines for the president and the treasurer",
    response_class=Response,
    responses=responses_of(401, 403, 404, 409, 422, extra=PDF_RESPONSE),
    openapi_extra=permission_extra(*READ),
)
def balancete_pdf(
    principal: Annotated[Principal, Depends(require_any(*READ))],
    scope: InSchool,
    db: TenantDb,
    period: PeriodQuery = None,
) -> Response:
    found = _sheet(db, scope, period)
    return pdf_response(balancete.render_pdf(found.sheet), f"balancete-{found.chosen}.pdf")


@router.post(
    "/balancete/balances",
    operation_id="balancete_balances_set",
    summary="Type the starting balance of the school, or the cash and invested of a month",
    status_code=201,
    response_model=None,
    responses=responses_of(401, 403, 404, 409, 422),
    openapi_extra={"x-permission": Permission.MONTHS_CLOSE.value},
)
def set_balance(
    body: BalanceIn,
    principal: Annotated[Principal, Depends(require(Permission.MONTHS_CLOSE))],
    scope: InSchool,
    db: TenantDb,
) -> dict[str, str]:
    """Insert-only: a correction is a new row and the latest counts; the audit trail keeps both."""
    start: date | None = None if body.period is None else month_bounds(body.period)[0]
    try:
        queries.insert_balance(
            db,
            organization_id=scope.organization_id,
            school_id=scope.school_id,
            kind=body.kind,
            period_start=start,
            bank_cents=body.bank_cents,
            cash_cents=body.cash_cents,
            investment_cents=body.investment_cents,
            user_id=principal.user_id,
        )
        db.commit()
    except DBAPIError:
        db.rollback()
        raise ProblemError(
            422, "balance_refused", "That balance cannot be saved", detail="Check the amounts."
        ) from None
    return {"status": "saved", "period": "" if start is None else period_of(start)}
