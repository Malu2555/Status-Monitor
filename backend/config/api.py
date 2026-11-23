"""Django Ninja API root: global throttle defaults + router mounting.

Conventions — HTTP status codes across all routers:
  200 OK · 201 created · 204 deleted · 400 bad request / plan limit ·
  401 unauthenticated · 403 CSRF mismatch (refresh only) · 404 not found ·
  422 validation / SSRF-blocked URL / interval below plan minimum ·
  429 rate limited · 503 billing provider not configured
"""

import logging

from django.conf import settings
from ninja import NinjaAPI
from ninja.openapi.docs import Swagger

from accounts.api import router as auth_router
from accounts.policy_api import router as policy_router
from billing.api import router as billing_router
from config.throttling import GlobalAnonThrottle, IpEnvelopeThrottle
from health.api import router as health_router
from monitors.admin_api import router as admin_run_router
from monitors.admin_api import scheduler_router
from monitors.api import public_router
from monitors.api import router as monitors_router
from monitors.statuspages_api import router as statuspages_router
from notifications.api import router as notifications_router

api = NinjaAPI(
    title="Status Monitor API",
    version="1.0.0",
    description="Private monitor management + free public status feed.",
    # Schema/docs are a development aid; keep them off the public production surface.
    docs=Swagger() if settings.DEBUG else None,  # type: ignore[arg-type]
    openapi_url="/openapi.json" if settings.DEBUG else None,
    throttle=[GlobalAnonThrottle("2000/h"), IpEnvelopeThrottle("1500/h")],
)

api.add_router("/auth", auth_router)
api.add_router("/policies", policy_router)
api.add_router("/monitors", monitors_router)
api.add_router("/statuspages", statuspages_router)
api.add_router("/notifications", notifications_router)
api.add_router("/admin/run", admin_run_router)
api.add_router("/admin/scheduler", scheduler_router)
api.add_router("/public", public_router)
api.add_router("/billing", billing_router)
api.add_router("", health_router)  # unauthenticated probes: GET /api/health

# --------------------------------------------------------------------------
# Startup guard: a credentialed SPA on another origin is rejected silently
# when no origin is allowed — warn loudly instead of failing mysteriously.
# --------------------------------------------------------------------------
if not settings.DEBUG and not settings.CORS_ALLOWED_ORIGINS:
    logging.getLogger("config").warning(
        "CORS_ALLOWED_ORIGINS is empty while DEBUG=False — browser clients on a "
        "different origin (e.g. https://<project>.vercel.app) will be rejected."
    )
