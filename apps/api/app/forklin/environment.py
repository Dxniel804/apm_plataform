"""GET /api/v1/environment: is the organization of this session in demonstration or for real?

The Central names the mode of an organization (`sandbox` or `production`,
docs/adr-ambiente-sandbox.md)
and this product records it (0033). Everybody who is signed in may ask, to show the notice of the
demonstration on the screen. With `FORKLIN_ENVIRONMENT_ENABLED` off the answer is `null`: nothing on
the screen depends on a mode the Central may not even be sending.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.deps import Principal, Settings, authenticated
from app.auth.responses import problem_responses
from app.db.tenant import TenantContext
from app.routers.deps import get_tenant_db, require_tenant_context

router = APIRouter(prefix="/environment", tags=["environment"])


def organization_environment(
    db: Session, settings: Any, organization_id: UUID
) -> Literal["sandbox", "production"] | None:
    """The environment of an organization, for the code that already has its tenant bound. None
    while FORKLIN_ENVIRONMENT_ENABLED is off (nothing depends on a mode not yet sent)."""
    if not settings.forklin_environment_enabled:
        return None
    value = db.execute(
        text("SELECT environment FROM organizations WHERE id = :organization"),
        {"organization": organization_id},
    ).scalar_one_or_none()
    return value if value in ("sandbox", "production") else None


def is_sandbox(db: Session, settings: Any, organization_id: UUID) -> bool:
    return organization_environment(db, settings, organization_id) == "sandbox"


TenantDb = Annotated[Session, Depends(get_tenant_db)]
Tenant = Annotated[TenantContext, Depends(require_tenant_context)]


class EnvironmentOut(BaseModel):
    environment: Literal["sandbox", "production"] | None


@router.get(
    "",
    operation_id="environment_get",
    summary="Whether the organization of the session is in demonstration or for real",
    response_model=EnvironmentOut,
    responses=problem_responses(401, 409),
)
def get_environment(
    _principal: Annotated[Principal, Depends(authenticated())],
    tenant: Tenant,
    db: TenantDb,
    settings: Settings,
) -> EnvironmentOut:
    return EnvironmentOut(
        environment=organization_environment(db, settings, tenant.organization_id)
    )
