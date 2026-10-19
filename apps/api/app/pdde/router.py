# ruff: noqa: E501  (openapi blocks)
"""The PDDE accountability: /api/v1/schools/{school_id}/pdde/...

One permission (`reconciliation:manage`, through `school_scope`): who manages the bank accounts also
classifies their lines. The year of the report and the month of the list are read in the time zone of
the school."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, school_scope
from app.pdde import report, service
from app.pdde.schemas import (
    CarryoverIn,
    CarryoverOut,
    ClassificationIn,
    DocumentIn,
    EntityIn,
    EntityOut,
    MonthOut,
    Program,
    YearOut,
)
from app.reports import queries as report_queries
from app.routers.deps import get_tenant_db
from app.statement.periods import PERIOD_PATTERN

router = APIRouter(prefix="/schools/{school_id}/pdde", tags=["pdde"])

TenantDb = Annotated[Session, Depends(get_tenant_db)]
Manage = Annotated[SchoolScope, Depends(school_scope(Permission.RECONCILIATION_MANAGE))]
_PERMISSION: dict[str, Any] = {"x-permission": Permission.RECONCILIATION_MANAGE.value}
_ERRORS = problem_responses(401, 403, 404, 409, 422)
Period = Annotated[str, Query(pattern=PERIOD_PATTERN, description="YYYY-MM")]
Year = Annotated[int, Query(ge=2000, le=2100)]


@router.get("/lines", operation_id="pdde_lines", response_model=MonthOut,
            summary="The lines of the PDDE accounts in a month, with what was decided about each one",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def month(scope: Manage, db: TenantDb, period: Period) -> MonthOut:
    return service.month_view(db, scope, period)


@router.get("/summary", operation_id="pdde_summary", response_model=YearOut,
            summary="The balance of each program in a year and what needs attention",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def summary(scope: Manage, db: TenantDb, year: Year) -> YearOut:
    return service.year_view(db, scope, year)


@router.post("/lines/{line_id}/classification", operation_id="pdde_classify", status_code=201,
             summary="Say what a line of the PDDE account is (a new decision: the latest counts)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def classify(line_id: UUID, body: ClassificationIn, scope: Manage, db: TenantDb) -> dict[str, str]:
    service.classify(db, scope, line_id, body)
    return {"status": "saved"}


@router.post("/lines/{line_id}/documents", operation_id="pdde_document_add", status_code=201,
             summary="Register the document that proves an expense line",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def add_document(line_id: UUID, body: DocumentIn, scope: Manage, db: TenantDb) -> dict[str, str]:
    new_id = service.add_document(db, scope, line_id, body)
    return {"id": str(new_id)}


@router.post("/documents/{document_id}/void", operation_id="pdde_document_void",
             summary="Void a mistaken document (it is never deleted)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def void_document(document_id: UUID, scope: Manage, db: TenantDb) -> dict[str, str]:
    service.void_document(db, scope, document_id)
    return {"status": "voided"}


def _file(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/report.csv", operation_id="pdde_report_csv", response_class=Response,
            summary="The year as a spreadsheet, in the order of the bank's screen",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def report_csv(scope: Manage, db: TenantDb, year: Year) -> Response:
    return _file(
        report.render_csv(service.report_rows(db, scope, year)),
        "text/csv; charset=utf-8",
        f"pdde-{year}.csv",
    )


@router.get("/report.pdf", operation_id="pdde_report_pdf", response_class=Response,
            summary="The year as a PDF, with the lines for the signatures",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def report_pdf(scope: Manage, db: TenantDb, year: Year) -> Response:
    lines = service.report_rows(db, scope, year)
    carry, _ = service.prior_balances(db, scope, year)
    programs, _ = service.balances(lines, carry)
    organization_name, school_name = report_queries.names(db, scope.school_id)
    pdf = report.render_pdf(
        lines=lines, programs=programs, year=year, organization_name=organization_name,
        school_name=school_name, generated_at=datetime.now(UTC),
    )  # fmt: skip
    return _file(pdf, "application/pdf", f"pdde-{year}.pdf")


@router.get("/entity", operation_id="pdde_entity", response_model=EntityOut | None,
            summary="The identification of the entity printed on the official forms",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def entity(scope: Manage, db: TenantDb) -> EntityOut | None:
    return service.get_entity(db, scope)


@router.post("/entity", operation_id="pdde_entity_save", status_code=201,
             summary="Save the name, the CNPJ and the address of the entity (the latest counts)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def save_entity(body: EntityIn, scope: Manage, db: TenantDb) -> dict[str, str]:
    service.save_entity(db, scope, body)
    return {"status": "saved"}


@router.get("/carryovers", operation_id="pdde_carryovers", response_model=list[CarryoverOut],
            summary="The balance that came from the year before, as the school typed it",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def carryovers(scope: Manage, db: TenantDb, year: Year) -> list[CarryoverOut]:
    return service.list_carryovers(db, scope, year)


@router.post("/carryovers", operation_id="pdde_carryover_save", status_code=201,
             summary="Type the balance that came from the year before (the latest counts)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def save_carryover(body: CarryoverIn, scope: Manage, db: TenantDb) -> dict[str, str]:
    service.save_carryover(db, scope, body)
    return {"status": "saved"}


@router.get("/forms/demonstrativo.pdf", operation_id="pdde_form_demonstrativo", response_class=Response,
            summary="The official form of the FNDE (Demonstrativo), one program and one year",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def demonstrativo(
    scope: Manage, db: TenantDb, year: Year, program: Program,
    program_label: Annotated[str | None, Query(max_length=60)] = None,
) -> Response:  # fmt: skip
    if (program == "OUTRO") != (program_label is not None):
        raise ProblemError(
            422,
            "validation_error",
            "Invalid request",
            errors=[{"field": "program_label", "code": "required_only_for_other"}],
        )
    pdf = service.demonstrativo_pdf(db, scope, year, program, program_label, datetime.now(UTC))
    return _file(pdf, "application/pdf", f"demonstrativo-{program.lower()}-{year}.pdf")
