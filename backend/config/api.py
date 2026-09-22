"""Django Ninja API root: global throttle defaults + router mounting.

Conventions — HTTP status codes across all routers:
  200 OK · 201 created · 204 deleted · 400 bad request / plan limit ·
  401 unauthenticated · 403 CSRF mismatch (refresh only) · 404 not found ·
  422 validation / SSRF-blocked URL / interval below plan minimum ·
  429 rate limited · 503 Stripe not configured
"""
from ninja import NinjaAPI

from accounts.api import router as auth_router
from billing.api import router as billing_router
from config.throttling import GlobalAnonThrottle
from health.api import router as health_router
from monitors.api import public_router
from monitors.api import router as monitors_router

api = NinjaAPI(
    title="Status Monitor API",
    version="1.0.0",
    description="Private monitor management + free public status feed.",
    throttle=GlobalAnonThrottle("2000/h"),
)

api.add_router("/auth", auth_router)
api.add_router("/monitors", monitors_router)
api.add_router("/public", public_router)
api.add_router("/billing", billing_router)
api.add_router("", health_router)  # unauthenticated probes: GET /api/health
