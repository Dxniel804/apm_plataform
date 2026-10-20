"""The campaigns the management writes: /api/v1/schools/{school_id}/campaigns...

Every route carries exactly one permission marker (`campaigns:manage`, through `school_scope`) and
checks that the school in the path is the school of the session (a different one is the same 404 as
a missing one). Routes that write commit inside the service. Errors are problem+json with a stable
`code`. What the families see is in `app.public.campaigns`.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.campaigns import orders, service
from app.campaigns.schemas import (
    BuyerList,
    CampaignCreate,
    CampaignDashboard,
    CampaignDetail,
    CampaignList,
    CampaignPatch,
    CampaignStatus,
    DeliveryChange,
    DeliveryResult,
    DeliveryStatus,
    ItemCreate,
    ItemPatch,
    OrderList,
    PaymentStatus,
)
from app.core.errors import PROBLEM_MEDIA_TYPE, ProblemError
from app.expenses.access import SchoolScope, school_scope
from app.routers.deps import get_tenant_db
from app.schemas.problem import Problem
from app.storage import (
    AttachmentStore,
    StorageNotFoundError,
    StorageSettings,
    get_attachment_store,
    get_storage_settings,
)
from app.storage.uploads import check_declared_length

router = APIRouter(prefix="/schools/{school_id}", tags=["campaigns"])

TenantDb = Annotated[Session, Depends(get_tenant_db)]
Manage = Annotated[SchoolScope, Depends(school_scope(Permission.CAMPAIGNS_MANAGE))]
Store = Annotated[AttachmentStore, Depends(get_attachment_store)]
Limits = Annotated[StorageSettings, Depends(get_storage_settings)]

_PERMISSION: dict[str, Any] = {"x-permission": Permission.CAMPAIGNS_MANAGE.value}


def _problem(description: str) -> dict[str, Any]:
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }


NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: _problem("not_found: unknown, or outside the session's school")
}


def _errors(*codes: int, extra: dict[int | str, dict[str, Any]] | None = None) -> dict[Any, Any]:
    """422 is always there: every route has a path parameter to validate."""
    return problem_responses(*sorted({*codes, 422}), extra={**NOT_FOUND, **(extra or {})})


@router.post(
    "/campaigns",
    operation_id="campaigns_create",
    summary="Create a campaign (a draft: nothing is on sale yet)",
    status_code=201,
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def create_campaign(body: CampaignCreate, scope: Manage, db: TenantDb) -> CampaignDetail:
    return service.create_campaign(db, scope, body)


@router.get(
    "/campaigns",
    operation_id="campaigns_list",
    summary="The campaigns of the school, the ones on sale first",
    response_model=CampaignList,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def list_campaigns(
    scope: Manage, db: TenantDb, status: Annotated[CampaignStatus | None, Query()] = None
) -> CampaignList:
    return service.list_campaigns(db, scope, status=status)


@router.get(
    "/campaigns/{campaign_id}",
    operation_id="campaigns_get",
    summary="One campaign with its products",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def get_campaign(campaign_id: UUID, scope: Manage, db: TenantDb) -> CampaignDetail:
    return service.get_campaign(db, scope, campaign_id)


@router.patch(
    "/campaigns/{campaign_id}",
    operation_id="campaigns_update",
    summary="Change the text or the dates of a campaign that has not ended",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def update_campaign(
    campaign_id: UUID, body: CampaignPatch, scope: Manage, db: TenantDb
) -> CampaignDetail:
    return service.update_campaign(db, scope, campaign_id, body)


@router.post(
    "/campaigns/{campaign_id}/activate",
    operation_id="campaigns_activate",
    summary="Put a draft on sale (it needs an active product)",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def activate_campaign(campaign_id: UUID, scope: Manage, db: TenantDb) -> CampaignDetail:
    return service.activate(db, scope, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/end",
    operation_id="campaigns_end",
    summary="End a campaign (final): nothing more is sold, the orders made stay",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def end_campaign(campaign_id: UUID, scope: Manage, db: TenantDb) -> CampaignDetail:
    return service.end(db, scope, campaign_id)


# --- products -------------------------------------------------------------------------------------


@router.post(
    "/campaigns/{campaign_id}/items",
    operation_id="campaign_items_create",
    summary="Add a product to a campaign that has not ended",
    status_code=201,
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def create_item(campaign_id: UUID, body: ItemCreate, scope: Manage, db: TenantDb) -> CampaignDetail:
    return service.add_item(db, scope, campaign_id, body)


@router.patch(
    "/campaigns/{campaign_id}/items/{item_id}",
    operation_id="campaign_items_update",
    summary="Change a product (a new price never touches an order already made)",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def update_item(
    campaign_id: UUID, item_id: UUID, body: ItemPatch, scope: Manage, db: TenantDb
) -> CampaignDetail:
    return service.update_item(db, scope, campaign_id, item_id, body)


# --- pictures -------------------------------------------------------------------------------------

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
                            "description": "A picture (PNG, JPEG, WebP) of at most 5 MiB.",
                        }
                    },
                }
            }
        },
    }
}
_UPLOAD_ERRORS = _errors(
    401,
    403,
    409,
    extra={
        411: _problem("length_required: the request must declare its size"),
        413: _problem("payload_too_large"),
        415: _problem("attachment_type_not_allowed"),
    },
)  # fmt: skip


async def _receive(
    request: Request,
    scope: SchoolScope,
    db: Session,
    store: AttachmentStore,
    limits: StorageSettings,
    campaign_id: UUID,
    item_id: UUID | None,
) -> CampaignDetail:
    """The size is bounded BEFORE the body is read (the declared length) and again while it is
    read. The form is parsed here, after the permission and the school were checked."""
    check_declared_length(request, min(limits.attachment_max_bytes, service.MAX_IMAGE_BYTES))
    form = await request.form(max_files=1, max_fields=2)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise service.invalid_field("file", "required")
        return await run_in_threadpool(
            service.set_image,
            db,
            scope,
            store,
            campaign_id,
            item_id,
            stream=upload.file,
            max_bytes=limits.attachment_max_bytes,
        )
    finally:
        await form.close()


@router.put(
    "/campaigns/{campaign_id}/image",
    operation_id="campaigns_cover_set",
    summary="Set the cover (multipart: `file`); the metadata of the photo is removed",
    response_model=CampaignDetail,
    responses=_UPLOAD_ERRORS,
    openapi_extra={**_PERMISSION, **_UPLOAD_BODY},
)
async def set_cover(
    request: Request, campaign_id: UUID, scope: Manage, db: TenantDb, store: Store, limits: Limits
) -> CampaignDetail:
    return await _receive(request, scope, db, store, limits, campaign_id, None)


@router.delete(
    "/campaigns/{campaign_id}/image",
    operation_id="campaigns_cover_clear",
    summary="Remove the cover",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def clear_cover(campaign_id: UUID, scope: Manage, db: TenantDb, store: Store) -> CampaignDetail:
    return service.clear_image(db, scope, store, campaign_id, None)


@router.put(
    "/campaigns/{campaign_id}/items/{item_id}/image",
    operation_id="campaign_items_image_set",
    summary="Set the picture of a product (multipart: `file`)",
    response_model=CampaignDetail,
    responses=_UPLOAD_ERRORS,
    openapi_extra={**_PERMISSION, **_UPLOAD_BODY},
)
async def set_item_image(
    request: Request,
    campaign_id: UUID,
    item_id: UUID,
    scope: Manage,
    db: TenantDb,
    store: Store,
    limits: Limits,
) -> CampaignDetail:
    return await _receive(request, scope, db, store, limits, campaign_id, item_id)


@router.delete(
    "/campaigns/{campaign_id}/items/{item_id}/image",
    operation_id="campaign_items_image_clear",
    summary="Remove the picture of a product",
    response_model=CampaignDetail,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def clear_item_image(
    campaign_id: UUID, item_id: UUID, scope: Manage, db: TenantDb, store: Store
) -> CampaignDetail:
    return service.clear_image(db, scope, store, campaign_id, item_id)


def _stream(image: Any, store: AttachmentStore) -> StreamingResponse:
    try:
        chunks = store.open(image["storage_key"])
    except StorageNotFoundError:
        raise ProblemError(500, "attachment_unavailable", "The file is not available") from None
    return StreamingResponse(
        chunks,
        media_type=image["content_type"],
        headers={
            "Content-Length": str(image["size_bytes"]),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )


_IMAGE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The picture",
        "content": {content_type: {} for content_type in service.IMAGE_TYPES},
    },
    **_errors(401, 403, 409),
}


@router.get(
    "/campaigns/{campaign_id}/image",
    operation_id="campaigns_cover_get",
    summary="The cover, for the management to see (a draft too)",
    response_class=StreamingResponse,
    responses=_IMAGE_RESPONSES,
    openapi_extra=_PERMISSION,
)
def get_cover(campaign_id: UUID, scope: Manage, db: TenantDb, store: Store) -> StreamingResponse:
    return _stream(service.image_for_download(db, scope, campaign_id, None), store)


@router.get(
    "/campaigns/{campaign_id}/items/{item_id}/image",
    operation_id="campaign_items_image_get",
    summary="The picture of a product, for the management to see (a draft too)",
    response_class=StreamingResponse,
    responses=_IMAGE_RESPONSES,
    openapi_extra=_PERMISSION,
)
def get_item_image(
    campaign_id: UUID, item_id: UUID, scope: Manage, db: TenantDb, store: Store
) -> StreamingResponse:
    return _stream(service.image_for_download(db, scope, campaign_id, item_id), store)


# --- what the management follows: the dashboard, the orders, their delivery, the PDF (0014) ---


@router.get(
    "/campaigns/{campaign_id}/dashboard",
    operation_id="campaigns_dashboard",
    summary="What the campaign collected, what it cost, what each product sold",
    response_model=CampaignDashboard,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def campaign_dashboard(campaign_id: UUID, scope: Manage, db: TenantDb) -> CampaignDashboard:
    return orders.dashboard(db, scope, campaign_id)


@router.get(
    "/campaigns/{campaign_id}/orders",
    operation_id="campaigns_orders",
    summary="The orders of the campaign, with payment and delivery",
    response_model=OrderList,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def campaign_orders(
    campaign_id: UUID,
    scope: Manage,
    db: TenantDb,
    payment: Annotated[PaymentStatus | None, Query()] = None,
    delivery: Annotated[DeliveryStatus | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> OrderList:
    return orders.list_orders(
        db, scope, campaign_id,
        payment=payment, delivery=delivery, search=search, limit=limit, offset=offset,
    )  # fmt: skip


@router.get(
    "/campaigns/{campaign_id}/buyers",
    operation_id="campaigns_buyers",
    summary="Who bought what: the paid orders grouped by guardian and student",
    response_model=BuyerList,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def campaign_buyers(campaign_id: UUID, scope: Manage, db: TenantDb) -> BuyerList:
    return orders.buyers(db, scope, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/orders/delivery",
    operation_id="campaigns_orders_delivery",
    summary="Mark (or unmark) the delivery of paid orders, up to 100 at once",
    response_model=DeliveryResult,
    responses=_errors(401, 403, 409),
    openapi_extra=_PERMISSION,
)
def change_delivery(
    campaign_id: UUID, body: DeliveryChange, scope: Manage, db: TenantDb
) -> DeliveryResult:
    return orders.change_delivery(db, scope, campaign_id, body)


@router.get(
    "/campaigns/{campaign_id}/report.pdf",
    operation_id="campaigns_report_pdf",
    summary="The PDF of the campaign: totals, products and every order",
    response_class=Response,
    responses=_errors(
        401, 403, 409,
        extra={200: {
            "description": "The PDF.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }},
    ),
    openapi_extra=_PERMISSION,
)  # fmt: skip
def campaign_report(campaign_id: UUID, scope: Manage, db: TenantDb) -> Response:
    content = orders.report_pdf(db, scope, campaign_id)
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="campanha-{str(campaign_id)[:8]}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
