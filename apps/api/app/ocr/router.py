"""Reading a receipt photo for an expense: /api/v1/schools/{school_id}/expenses/ocr.

The photo goes to the OCR container and comes back as a SUGGESTION for the form. Nothing is stored
and no expense is created here: the person confirms the fields and sends the same photo as the
attachment of the expense, through the usual routes. Permission: `expenses:submit`.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.core.errors import PROBLEM_MEDIA_TYPE, ProblemError
from app.expenses.access import SchoolScope, school_scope
from app.expenses.service import invalid_field
from app.ocr import service
from app.ocr.config import get_ocr_settings
from app.ocr.limits import ConcurrencyGate, UserRateLimiter
from app.ocr.provider import HttpOcrProvider, OcrProvider
from app.ocr.schemas import OcrStatus, OcrSuggestion
from app.routers.deps import get_tenant_db
from app.schemas.problem import Problem
from app.storage import StorageSettings, get_storage_settings
from app.storage.uploads import check_declared_length

router = APIRouter(prefix="/schools/{school_id}", tags=["expense-ocr"])

TenantDb = Annotated[Session, Depends(get_tenant_db)]
CanSubmit = Annotated[SchoolScope, Depends(school_scope(Permission.EXPENSES_SUBMIT))]
Limits = Annotated[StorageSettings, Depends(get_storage_settings)]


@dataclass(frozen=True)
class OcrRuntime:
    """What a request needs to read: the provider (None when the feature is off) and the brakes."""

    provider: OcrProvider | None
    limiter: UserRateLimiter
    gate: ConcurrencyGate


@lru_cache
def get_ocr_runtime() -> OcrRuntime:
    """FastAPI dependency, built once per process (the limits live in it). Tests replace it with
    `app.dependency_overrides`, or clear this cache after changing the environment."""
    settings = get_ocr_settings()
    return OcrRuntime(
        provider=HttpOcrProvider(settings) if settings.ocr_enabled else None,
        limiter=UserRateLimiter(settings.ocr_user_per_minute),
        gate=ConcurrencyGate(settings.ocr_max_concurrency),
    )


Runtime = Annotated[OcrRuntime, Depends(get_ocr_runtime)]

_PERMISSION: dict[str, Any] = {"x-permission": Permission.EXPENSES_SUBMIT.value}


def _problem(description: str) -> dict[str, Any]:
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }


_ERRORS = problem_responses(401, 403, 404, 409, 422, 429, extra={
    411: _problem("length_required: the request must declare its size"),
    413: _problem("payload_too_large"),
    415: _problem("attachment_type_not_allowed: photos only"),
    503: _problem("ocr_unavailable or ocr_busy: fill the expense by hand, or try again"),
    504: _problem("ocr_timeout: fill the expense by hand"),
})  # fmt: skip

_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "A photo of the receipt (PNG, JPEG, WebP).",
                        }
                    },
                }
            }
        },
    }
}


@router.get(
    "/expenses/ocr",
    operation_id="expense_ocr_status",
    summary="Whether the reading of receipts is on",
    response_model=OcrStatus,
    responses=problem_responses(401, 403, 404, 409, 422),
    openapi_extra=_PERMISSION,
)
def ocr_status(scope: CanSubmit, runtime: Runtime) -> OcrStatus:
    return OcrStatus(enabled=runtime.provider is not None)


@router.post(
    "/expenses/ocr",
    operation_id="expense_ocr_read",
    summary="Read a receipt photo and suggest the fields of the expense (nothing is stored)",
    response_model=OcrSuggestion,
    responses=_ERRORS,
    openapi_extra={**_PERMISSION, **_UPLOAD_BODY},
)
async def read_receipt(
    request: Request, scope: CanSubmit, db: TenantDb, runtime: Runtime, limits: Limits
) -> OcrSuggestion:
    """The cheap refusals come first (off, too big, too many), then the form is parsed and the photo
    is read in a worker thread: the model is slow and must not block the event loop."""
    provider = runtime.provider
    if provider is None:
        raise ProblemError(
            503, "ocr_unavailable", "The reading is not available: fill the expense by hand"
        )
    check_declared_length(request, limits.attachment_max_bytes)
    wait = runtime.limiter.take(scope.user_id)
    if wait:
        raise ProblemError(
            429,
            "rate_limited",
            "Too many readings in a row",
            headers={"Retry-After": str(wait)},
        )
    form = await request.form(max_files=1, max_fields=2)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise invalid_field("file", "required")
        return await run_in_threadpool(
            service.read_receipt,
            db,
            scope,
            provider,
            runtime.gate,
            upload.file,
            max_bytes=limits.attachment_max_bytes,
        )
    finally:
        await form.close()
