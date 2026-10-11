"""Staff requests and their photos: /api/v1/schools/{school_id}/requests...

Every route carries exactly one permission marker (through `school_scope`) and checks that the
school in the path is the school of the session (a different one is the same 404 as a missing one).
Routes that write commit inside the service. Errors are problem+json with a stable `code`.
"""

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.core.errors import PROBLEM_MEDIA_TYPE, ProblemError
from app.expenses.access import SchoolScope, school_scope
from app.routers.deps import get_tenant_db
from app.schemas.problem import Problem
from app.staff_requests import service
from app.staff_requests.schemas import (
    RequestAttachmentOut,
    RequestCategory,
    RequestCreate,
    RequestDetail,
    RequestPage,
    RequestStatus,
    ResolveRequest,
)
from app.storage import (
    AttachmentStore,
    StorageNotFoundError,
    StorageSettings,
    get_attachment_store,
    get_storage_settings,
)
from app.storage.uploads import check_declared_length

router = APIRouter(prefix="/schools/{school_id}", tags=["staff-requests"])

TenantDb = Annotated[Session, Depends(get_tenant_db)]

_SUBMIT = (Permission.REQUESTS_SUBMIT,)
_READ = (Permission.REQUESTS_READ_OWN, Permission.REQUESTS_READ_ALL)
_MANAGE = (Permission.REQUESTS_MANAGE,)

CanSubmit = Annotated[SchoolScope, Depends(school_scope(*_SUBMIT))]
CanRead = Annotated[SchoolScope, Depends(school_scope(*_READ))]
CanManage = Annotated[SchoolScope, Depends(school_scope(*_MANAGE))]
Store = Annotated[AttachmentStore, Depends(get_attachment_store)]
Limits = Annotated[StorageSettings, Depends(get_storage_settings)]


def _permission(*permissions: Permission) -> dict[str, Any]:
    """`x-permission` is what the route walk checks; `x-permission-any` lists the alternatives of a
    route open to more than one permission."""
    extra: dict[str, Any] = {"x-permission": permissions[0].value}
    if len(permissions) > 1:
        extra["x-permission-any"] = [permission.value for permission in permissions]
    return extra


def _problem(description: str) -> dict[str, Any]:
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }


NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: _problem("not_found: unknown, outside the session's school, or not yours to see")
}


def _errors(*codes: int, extra: dict[int | str, dict[str, Any]] | None = None) -> dict[Any, Any]:
    """The problems a route can answer. 422 is always there: every route has a path parameter to
    validate, and the framework would otherwise document its own 422 instead of the problem."""
    return problem_responses(*sorted({*codes, 422}), extra={**NOT_FOUND, **(extra or {})})


@router.post(
    "/requests",
    operation_id="staff_requests_create",
    summary="Open a request to the management",
    status_code=201,
    response_model=RequestDetail,
    responses=_errors(401, 403, 409, 422),
    openapi_extra=_permission(*_SUBMIT),
)
def create_request(body: RequestCreate, scope: CanSubmit, db: TenantDb) -> RequestDetail:
    return service.create_request(db, scope, body)


@router.get(
    "/requests",
    operation_id="staff_requests_list",
    summary="List requests (all of them with requests:read_all, otherwise your own)",
    response_model=RequestPage,
    responses=_errors(401, 403, 409, 422),
    openapi_extra=_permission(*_READ),
)
def list_requests(
    scope: CanRead,
    db: TenantDb,
    status: Annotated[RequestStatus | None, Query()] = None,
    category: Annotated[RequestCategory | None, Query()] = None,
    period: Annotated[
        str | None, Query(max_length=7, description="A month, YYYY-MM, in the school's time zone")
    ] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RequestPage:
    return service.list_requests(
        db, scope, status=status, category=category, period=period, cursor=cursor, limit=limit
    )


@router.get(
    "/requests/{request_id}",
    operation_id="staff_requests_get",
    summary="One request, with its photos",
    response_model=RequestDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_permission(*_READ),
)
def get_request(request_id: UUID, scope: CanRead, db: TenantDb) -> RequestDetail:
    return service.get_request(db, scope, request_id)


# --- photos ---------------------------------------------------------------------------------------

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
                            "description": "A photo (PNG, JPEG, WebP), within the limit.",
                        }
                    },
                }
            }
        },
    }
}


@router.post(
    "/requests/{request_id}/attachments",
    operation_id="staff_request_attachments_upload",
    summary="Attach a photo (multipart: `file`)",
    status_code=201,
    response_model=RequestAttachmentOut,
    responses=_errors(
        401,
        403,
        409,
        422,
        extra={
            411: _problem("length_required: the request must declare its size"),
            413: _problem("payload_too_large"),
            415: _problem("attachment_type_not_allowed"),
        },
    ),  # fmt: skip
    openapi_extra={**_permission(*_SUBMIT), **_UPLOAD_BODY},
)
async def upload_attachment(
    request: Request,
    request_id: UUID,
    scope: CanSubmit,
    db: TenantDb,
    store: Store,
    limits: Limits,
) -> RequestAttachmentOut:
    """The size is bounded BEFORE the body is read (the declared length), and again while the file
    is streamed to the store. The form is parsed here, after the permission and the school were
    checked, so a caller who may not upload costs nothing."""
    check_declared_length(request, limits.attachment_max_bytes)
    form = await request.form(max_files=1, max_fields=2)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise service.invalid_field("file", "required")
        return await run_in_threadpool(
            service.add_attachment,
            db,
            scope,
            store,
            request_id,
            file_name=upload.filename,
            stream=upload.file,
            max_bytes=limits.attachment_max_bytes,
        )
    finally:
        await form.close()


def _content_disposition(name: str) -> str:
    fallback = "".join(
        ch if ch.isascii() and ch.isprintable() and ch not in '"\\%' else "_" for ch in name
    )
    return f"attachment; filename=\"{fallback or 'foto'}\"; filename*=UTF-8''{quote(name, safe='')}"


@router.get(
    "/requests/{request_id}/attachments/{attachment_id}",
    operation_id="staff_request_attachments_download",
    summary="Download a photo (whoever can see the request)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The photo, as an attachment",
            "content": {content_type: {} for content_type in service.PHOTO_TYPES},
        },
        **_errors(401, 403, 409),
    },
    openapi_extra=_permission(*_READ),
)
def download_attachment(
    request_id: UUID, attachment_id: UUID, scope: CanRead, db: TenantDb, store: Store
) -> StreamingResponse:
    attachment = service.attachment_for_download(db, scope, request_id, attachment_id)
    try:
        chunks = store.open(attachment["storage_key"])
    except StorageNotFoundError:
        raise ProblemError(500, "attachment_unavailable", "The file is not available") from None
    return StreamingResponse(
        chunks,
        media_type=attachment["content_type"],
        headers={
            "Content-Disposition": _content_disposition(attachment["file_name"]),
            "Content-Length": str(attachment["size_bytes"]),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )


# --- actions --------------------------------------------------------------------------------------

_STATE_ERRORS = _errors(401, 403, 409, 422)


@router.post(
    "/requests/{request_id}/start",
    operation_id="staff_requests_start",
    summary="The management took the request (OPEN to IN_PROGRESS)",
    response_model=RequestDetail,
    responses=_STATE_ERRORS,
    openapi_extra=_permission(*_MANAGE),
)
def start_request(request_id: UUID, scope: CanManage, db: TenantDb) -> RequestDetail:
    return service.start(db, scope, request_id)


@router.post(
    "/requests/{request_id}/resolve",
    operation_id="staff_requests_resolve",
    summary="The management answered it (to RESOLVED), with an optional note for the author",
    response_model=RequestDetail,
    responses=_STATE_ERRORS,
    openapi_extra=_permission(*_MANAGE),
)
def resolve_request(
    request_id: UUID, scope: CanManage, db: TenantDb, body: ResolveRequest | None = None
) -> RequestDetail:
    return service.resolve(db, scope, request_id, (body or ResolveRequest()).note)


@router.post(
    "/requests/{request_id}/cancel",
    operation_id="staff_requests_cancel",
    summary="The author withdrew the request (while it is open)",
    response_model=RequestDetail,
    responses=_STATE_ERRORS,
    openapi_extra=_permission(*_SUBMIT),
)
def cancel_request(request_id: UUID, scope: CanSubmit, db: TenantDb) -> RequestDetail:
    return service.cancel(db, scope, request_id)
