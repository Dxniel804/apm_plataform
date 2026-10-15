# ruff: noqa: E501  (openapi blocks)
"""The bank reconciliation: /api/v1/schools/{school_id}/reconciliation/...

One permission (`reconciliation:manage`, through `school_scope`). The file is bounded BEFORE it is
read (the declared length) and again while it is read; the form is parsed after the permission and
the school were checked."""

from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.core.errors import ProblemError
from app.expenses.access import SchoolScope, school_scope
from app.ocr.limits import UserRateLimiter
from app.reconciliation import service
from app.reconciliation.schemas import (
    AccountCreate,
    AccountOut,
    AccountPatch,
    ClosingBalanceOut,
    CsvPreviewOut,
    ImportList,
    ImportOut,
    LineAction,
    LineActionOut,
    ReconciliationOut,
)
from app.reconciliation.service import UPLOAD_MAX_BYTES
from app.routers.deps import get_tenant_db
from app.storage.uploads import check_declared_length

router = APIRouter(prefix="/schools/{school_id}/reconciliation", tags=["reconciliation"])

UPLOADS_PER_MINUTE = 10


@lru_cache
def get_upload_limiter() -> UserRateLimiter:
    """At most `UPLOADS_PER_MINUTE` statement files (sent or looked at) per person: reading a PDF
    costs CPU. In the memory of this process, like the one of the receipt reading. Tests replace
    it with `app.dependency_overrides`."""
    return UserRateLimiter(UPLOADS_PER_MINUTE)


UploadLimiter = Annotated[UserRateLimiter, Depends(get_upload_limiter)]


def _take(limiter: UserRateLimiter, scope: SchoolScope) -> None:
    wait = limiter.take(scope.user_id)
    if wait:
        raise ProblemError(
            429, "rate_limited", "Too many files in a row", headers={"Retry-After": str(wait)}
        )


TenantDb = Annotated[Session, Depends(get_tenant_db)]
Manage = Annotated[SchoolScope, Depends(school_scope(Permission.RECONCILIATION_MANAGE))]
_PERMISSION: dict[str, Any] = {"x-permission": Permission.RECONCILIATION_MANAGE.value}
_ERRORS = problem_responses(401, 403, 404, 409, 422)
_UPLOAD_ERRORS = problem_responses(
    401, 403, 404, 409, 422,
    extra={
        411: {"description": "length_required: the request must declare its size"},
        413: {"description": "payload_too_large: OFX and CSV are at most 2 MiB, a PDF 5 MiB"},
        429: {"description": "rate_limited: at most 10 files a minute per person"},
    },
)  # fmt: skip
_UPLOAD_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file", "bank_account_id"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "An OFX or CSV file (up to 2 MiB) or a PDF (up to 5 MiB).",
                        },
                        "bank_account_id": {"type": "string", "format": "uuid"},
                        "profile": {
                            "type": "string",
                            "description": "CSV only: the column map (JSON), kept on the account.",
                        },
                    },
                }
            }
        },
    }
}


@router.get("/accounts", operation_id="reconciliation_accounts", response_model=list[AccountOut],
            summary="The bank accounts of the school", responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def list_accounts(scope: Manage, db: TenantDb) -> list[AccountOut]:
    return service.list_accounts(db, scope)


@router.post("/accounts", operation_id="reconciliation_account_create", status_code=201,
             response_model=AccountOut, summary="Add a bank account (only its last digits)",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def create_account(body: AccountCreate, scope: Manage, db: TenantDb) -> AccountOut:
    return service.create_account(db, scope, body)


@router.patch("/accounts/{account_id}", operation_id="reconciliation_account_update",
              response_model=AccountOut, summary="Change or switch off a bank account",
              responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def update_account(account_id: UUID, body: AccountPatch, scope: Manage, db: TenantDb) -> AccountOut:
    return service.update_account(db, scope, account_id, body)


@router.get("/imports", operation_id="reconciliation_imports", response_model=ImportList,
            summary="The statements already imported, newest first", responses=_ERRORS,
            openapi_extra=_PERMISSION)  # fmt: skip
def list_imports(scope: Manage, db: TenantDb) -> ImportList:
    return service.list_imports(db, scope)


@router.post("/imports", operation_id="reconciliation_import", status_code=201,
             response_model=ImportOut, summary="Import a statement: OFX, CSV or PDF (multipart)",
             responses=_UPLOAD_ERRORS,
             openapi_extra={**_PERMISSION, **_UPLOAD_BODY})  # fmt: skip
async def import_statement(
    request: Request, scope: Manage, db: TenantDb, limiter: UploadLimiter
) -> ImportOut:
    check_declared_length(request, UPLOAD_MAX_BYTES)
    _take(limiter, scope)
    form = await request.form(max_files=1, max_fields=4)
    try:
        upload = form.get("file")
        raw_account = form.get("bank_account_id")
        if not isinstance(upload, UploadFile):
            raise service._invalid("file", "required")
        try:
            account_id = UUID(str(raw_account))
        except ValueError:
            raise service._invalid("bank_account_id", "required") from None
        raw_profile = form.get("profile")
        profile = raw_profile if isinstance(raw_profile, str) else None
        return await run_in_threadpool(
            service.import_file, db, scope, account_id, upload.file, profile
        )
    finally:
        await form.close()


@router.get("/imports/{import_id}", operation_id="reconciliation_compare", response_model=ReconciliationOut,
            summary="The statement against the ledger: matched, missing and divergent",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def compare(import_id: UUID, scope: Manage, db: TenantDb) -> ReconciliationOut:
    return service.compare(db, scope, import_id)


@router.post("/lines/{line_id}/actions", operation_id="reconciliation_line_action", status_code=201,
             response_model=LineActionOut,
             summary="Register what the bank shows (a Pix, a transfer, a fee) or ignore the line, with a reason",
             responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def act_on_line(line_id: UUID, body: LineAction, scope: Manage, db: TenantDb) -> LineActionOut:
    return service.act_on_line(db, scope, line_id, body)


@router.get("/closing-balance", operation_id="reconciliation_closing_balance",
            response_model=ClosingBalanceOut,
            summary="The balance of the last bank statements up to the end of a month (YYYY-MM)",
            responses=_ERRORS, openapi_extra=_PERMISSION)  # fmt: skip
def closing_balance(
    scope: Manage, db: TenantDb, period: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
) -> ClosingBalanceOut:
    return service.closing_balance(db, scope, period)


@router.post("/imports/preview", operation_id="reconciliation_import_preview", response_model=CsvPreviewOut,
             summary="Look at a file before importing it: the first rows of a CSV and the columns it looks like",
             responses=_UPLOAD_ERRORS, openapi_extra={**_PERMISSION, **_UPLOAD_BODY})  # fmt: skip
async def preview_statement(
    request: Request, scope: Manage, db: TenantDb, limiter: UploadLimiter
) -> CsvPreviewOut:
    check_declared_length(request, UPLOAD_MAX_BYTES)
    _take(limiter, scope)
    form = await request.form(max_files=1, max_fields=4)
    try:
        upload = form.get("file")
        raw_account = form.get("bank_account_id")
        if not isinstance(upload, UploadFile):
            raise service._invalid("file", "required")
        try:
            account_id = UUID(str(raw_account))
        except ValueError:
            raise service._invalid("bank_account_id", "required") from None
        return await run_in_threadpool(service.preview, db, scope, account_id, upload.file)
    finally:
        await form.close()
