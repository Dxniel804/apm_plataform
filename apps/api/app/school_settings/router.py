"""The settings and the public link of a school: /api/v1/schools/{school_id}/...

One permission (`school_settings:manage`, through `school_scope`) and the school of the path must be
the school of the session (any other is the same 404 as a missing one)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import Settings
from app.auth.permissions import Permission
from app.auth.responses import problem_responses
from app.expenses.access import SchoolScope, school_scope
from app.routers.deps import get_tenant_db
from app.school_settings import service
from app.school_settings.poster import render_poster
from app.school_settings.schemas import PublicLinkOut, SettingsOut, SettingsPatch

router = APIRouter(prefix="/schools/{school_id}", tags=["school-settings"])

TenantDb = Annotated[Session, Depends(get_tenant_db)]
Manage = Annotated[SchoolScope, Depends(school_scope(Permission.SCHOOL_SETTINGS_MANAGE))]
_PERMISSION: dict[str, Any] = {"x-permission": Permission.SCHOOL_SETTINGS_MANAGE.value}


@router.get(
    "/settings",
    operation_id="school_settings_get",
    summary="The amounts, the text and the goals of the school",
    response_model=SettingsOut,
    responses=problem_responses(401, 403, 404, 409, 422),
    openapi_extra=_PERMISSION,
)
def get_settings(scope: Manage, db: TenantDb) -> SettingsOut:
    return service.get_settings(db, scope)


@router.patch(
    "/settings",
    operation_id="school_settings_update",
    summary="Change the suggested amounts, the free amount text and the goals",
    response_model=SettingsOut,
    responses=problem_responses(401, 403, 404, 409, 422),
    openapi_extra=_PERMISSION,
)
def update_settings(body: SettingsPatch, scope: Manage, db: TenantDb) -> SettingsOut:
    return service.update_settings(db, scope, body)


@router.get(
    "/public-link",
    operation_id="school_public_link",
    summary="The address the families open to contribute to this school",
    response_model=PublicLinkOut,
    responses=problem_responses(401, 403, 404, 409, 422),
    openapi_extra=_PERMISSION,
)
def get_public_link(scope: Manage, db: TenantDb, settings: Settings) -> PublicLinkOut:
    return service.public_link(db, scope, settings)


@router.get(
    "/public-link/poster.pdf",
    operation_id="school_public_link_poster",
    summary="An A4 poster with the QR code of the public link",
    response_class=Response,
    responses=problem_responses(
        401, 403, 404, 409, 422,
        extra={200: {
            "description": "The PDF.",
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
        }},
    ),
    openapi_extra=_PERMISSION,
)  # fmt: skip
def get_poster(scope: Manage, db: TenantDb, settings: Settings) -> Response:
    link = service.public_link(db, scope, settings)
    return Response(
        render_poster(school_name=link.school_name, url=link.url),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cartaz-{link.slug}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
