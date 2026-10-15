from fastapi import APIRouter

from app.contributions.router import router as contributions_router
from app.dev.router import router as dev_router
from app.pix.webhook import router as webhook_router
from app.public.campaigns import media_router as public_media_router
from app.public.campaigns import router as public_campaigns_router
from app.public.router import router as public_router
from app.routers import health
from app.routers.v1 import auth, employees, forklin, invitations

# Web and API share one origin behind a proxy; the API lives under /api (no CORS).
api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth.router)
v1_router.include_router(invitations.router)
v1_router.include_router(employees.router)
v1_router.include_router(forklin.router)
v1_router.include_router(public_router)
v1_router.include_router(public_campaigns_router)
v1_router.include_router(public_media_router)
v1_router.include_router(webhook_router)
v1_router.include_router(contributions_router)
v1_router.include_router(dev_router)
api_router.include_router(v1_router)
