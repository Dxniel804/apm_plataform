# ruff: noqa: E501  (openapi blocks)
"""The tax guides: /api/v1/schools/{school_id}/tax/...

One permission (`months:close`, through `school_scope`): who closes the month also keeps the retentions."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.expenses.access import SchoolScope, school_scope
from app.routers.deps import get_tenant_db
from app.statement.periods import PERIOD_PATTERN
from app.tax import service
from app.tax.schemas import MonthOut, PreviewOut, Provider, RetentionIn, RuleIn, RulesOut

router = APIRouter(prefix="/schools/{school_id}/tax", tags=["tax"])

TenantDb = Annotated[Session, Depends(get_tenant_db)]
Manage = Annotated[SchoolScope, Depends(school_scope(Permission.MONTHS_CLOSE))]
_PERMISSION: dict[str, Any] = {"x-permission": Permission.MONTHS_CLOSE.value}
_ERRORS = problem_responses(401, 403, 404, 409, 422)


@router.get("/rules", operation_id="tax_rules", response_model=RulesOut,
            summary="The rules of the school (latest versions) and unvalidated suggestions",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def rules(scope: Manage, db: TenantDb) -> RulesOut:
    return service.list_rules(db, scope)


@router.post("/rules", operation_id="tax_rule_save", status_code=201,
             summary="Save a rule (a new version of its key; validated only if said so)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def save_rule(body: RuleIn, scope: Manage, db: TenantDb) -> dict[str, str]:
    service.save_rule(db, scope, body)
    return {"status": "saved"}


@router.get("/preview", operation_id="tax_preview", response_model=PreviewOut,
            summary="What would be retained (nothing is saved)",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def preview(
    scope: Manage, db: TenantDb, rule_id: UUID, provider_kind: Provider,
    gross_cents: Annotated[int, Query(ge=1, le=100_000_000_000)],
) -> PreviewOut:  # fmt: skip
    return service.preview(db, scope, rule_id, provider_kind, gross_cents)


@router.get("/month", operation_id="tax_month", response_model=MonthOut,
            summary="The retentions of a month and the guides they make",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def month(
    scope: Manage, db: TenantDb, period: Annotated[str, Query(pattern=PERIOD_PATTERN)]
) -> MonthOut:
    return service.month_view(db, scope, period)


@router.post("/retentions", operation_id="tax_retention_add", status_code=201,
             summary="Register a retention on a service the APM paid",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def add(body: RetentionIn, scope: Manage, db: TenantDb) -> dict[str, str]:
    return {"id": str(service.register(db, scope, body))}


@router.post("/retentions/{retention_id}/void", operation_id="tax_retention_void",
             summary="Void a mistaken retention (it is never deleted)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def void(retention_id: UUID, scope: Manage, db: TenantDb) -> dict[str, str]:
    service.void(db, scope, retention_id)
    return {"status": "voided"}
