"""The campaigns on sale at a school, for the families (no login): /api/v1/public/schools/{slug}/...

Same rules as the rest of the public flow: the school comes from the slug of the URL, an unknown or
closed campaign is the one 404, writes need an Idempotency-Key and are rate limited per address.
The order never carries a price or a total (see `app.public.campaign_service`). The pictures are
public once the campaign is on sale, so they have their own router with a cache policy of their own;
everything else answers `private, no-store` like the other public routes.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.deps import Db, Settings, public
from app.auth.ratelimit import client_ip
from app.auth.responses import problem_responses
from app.core.errors import ProblemError
from app.db.request_context import bind_request_context
from app.db.tenant import TenantContext, bind_tenant
from app.public import campaign_service, service
from app.public.router import _private, _state_out
from app.public.schemas import (
    ContributionCreatedOut,
    OrderIn,
    PublicCampaignList,
    PublicCampaignOut,
    PublicCampaignSummary,
    PublicItemOut,
)
from app.storage import AttachmentStore, StorageNotFoundError, get_attachment_store

router = APIRouter(
    prefix="/public/schools/{slug}",
    tags=["public"],
    dependencies=[Depends(public()), Depends(_private)],
)
# The pictures: public, cacheable for a few minutes, never executed (nosniff and a sandbox).
media_router = APIRouter(
    prefix="/public/schools/{slug}", tags=["public"], dependencies=[Depends(public())]
)

Store = Annotated[AttachmentStore, Depends(get_attachment_store)]

_PICTURE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The picture",
        "content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}},
    },
    **problem_responses(404, 422),
}


def _school(db: Session, slug: str) -> service.PublicSchool:
    """The school of the slug with the session bound to it, or the one 404."""
    bind_request_context(db, actor_type="PUBLIC")
    school = service.resolve_school(db, slug)
    if school is None:
        raise service.not_found()
    bind_tenant(db, TenantContext(school.organization_id, school.school_id))
    return school


@router.get(
    "/campaigns",
    operation_id="public_campaigns",
    summary="The campaigns on sale at the school",
    response_model=PublicCampaignList,
    responses=problem_responses(404, 422),
)
def list_campaigns(slug: str, db: Db) -> PublicCampaignList:
    school = _school(db, slug)
    rows = campaign_service.list_open(db, school)
    return PublicCampaignList(
        campaigns=[PublicCampaignSummary.model_validate(dict(row)) for row in rows]
    )


@router.get(
    "/campaigns/{campaign_id}",
    operation_id="public_campaign",
    summary="One campaign on sale, with its products and their current prices",
    response_model=PublicCampaignOut,
    responses=problem_responses(404, 422),
)
def get_campaign(slug: str, campaign_id: uuid.UUID, db: Db) -> PublicCampaignOut:
    school = _school(db, slug)
    campaign = campaign_service.open_campaign(db, school, campaign_id)
    if campaign is None:
        raise service.not_found()
    items = [
        PublicItemOut.model_validate(dict(item))
        for item in campaign_service.open_items(db, school, campaign_id)
    ]
    return PublicCampaignOut.model_validate({**dict(campaign), "items": items})


@router.post(
    "/campaigns/{campaign_id}/orders",
    operation_id="public_campaign_order",
    summary="Order products: creates the contribution and its Pix charge",
    status_code=201,
    response_model=ContributionCreatedOut,
    responses=problem_responses(404, 409, 422, 429, 501),
)
def create_order(
    slug: str,
    campaign_id: uuid.UUID,
    body: OrderIn,
    request: Request,
    db: Db,
    settings: Settings,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ContributionCreatedOut:
    """The server reads the current price of every product and adds them up: the body has only
    which products and how many. The `Idempotency-Key` (a uuid made by the page for each attempt)
    makes a repeated POST answer with the same order instead of creating another."""
    bind_request_context(db, actor_type="PUBLIC")
    try:
        key = uuid.UUID(idempotency_key or "")
    except ValueError:
        raise ProblemError(
            422,
            "validation_error",
            "Invalid request",
            errors=[{"field": "Idempotency-Key", "code": "required"}],
        ) from None
    service.guard_creation(db, settings, client_ip(request.client.host if request.client else None))
    school = service.resolve_school(db, slug)
    if school is None:
        db.commit()  # the attempt still counts against the client address
        raise service.not_found()
    bind_tenant(db, TenantContext(school.organization_id, school.school_id))
    token, state = campaign_service.create_order(db, settings, school, campaign_id, key, body)
    db.commit()
    return ContributionCreatedOut(token=token, **_state_out(state).model_dump())


# --- the pictures ---------------------------------------------------------------------------------


def _picture(request: Request, image: Any, store: AttachmentStore) -> Response:
    """The picture, with an ETag (its sha256) so a browser asks again cheaply."""
    etag = f'"{image["sha256"][:32]}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=300, must-revalidate",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Referrer-Policy": "no-referrer",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    try:
        chunks = store.open(image["storage_key"])
    except StorageNotFoundError:
        raise service.not_found() from None
    return StreamingResponse(
        chunks,
        media_type=image["content_type"],
        headers={**headers, "Content-Length": str(image["size_bytes"])},
    )


@media_router.get(
    "/campaigns/{campaign_id}/cover",
    operation_id="public_campaign_cover",
    summary="The cover of a campaign on sale",
    response_class=StreamingResponse,
    responses=_PICTURE,
)
def get_cover(
    slug: str, campaign_id: uuid.UUID, request: Request, db: Db, store: Store
) -> Response:
    school = _school(db, slug)
    image = campaign_service.cover_image(db, school, campaign_id)
    if image is None:
        raise service.not_found()
    return _picture(request, image, store)


@media_router.get(
    "/campaigns/{campaign_id}/items/{item_id}/image",
    operation_id="public_campaign_item_image",
    summary="The picture of a product of a campaign on sale",
    response_class=StreamingResponse,
    responses=_PICTURE,
)
def get_item_image(
    slug: str, campaign_id: uuid.UUID, item_id: uuid.UUID, request: Request, db: Db, store: Store
) -> Response:
    school = _school(db, slug)
    image = campaign_service.item_image(db, school, campaign_id, item_id)
    if image is None:
        raise service.not_found()
    return _picture(request, image, store)
