"""Rate-limit classes with isolated cache buckets.

django-ninja's throttles bucket by `scope` only (the rate string is not part
of the cache key), so every distinct rate needs its own scope/subclass —
otherwise two rates would silently share one bucket.
"""
from django.conf import settings
from ninja.throttling import AnonRateThrottle, AuthRateThrottle, BaseThrottle


class _TestAwareThrottle(BaseThrottle):
    """Skips throttling while the Django test runner is active."""

    def allow_request(self, request):
        if getattr(settings, "DISABLE_THROTTLING", False):
            return True
        return super().allow_request(request)


class AuthAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """5 req/min per IP — registration, login, refresh (brute-force protection)."""

    scope = "auth_anon"


class SessionAuthThrottle(_TestAwareThrottle, AuthRateThrottle):
    """Per-user limit for lightweight session endpoints (me/logout)."""

    scope = "session_auth"


class PublicAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """60 req/min per IP — free public status feed + Stripe webhook."""

    scope = "public_anon"


class MonitorAuthThrottle(_TestAwareThrottle, AuthRateThrottle):
    """Per-user limit for monitor CRUD and billing endpoints."""

    scope = "monitor_auth"


class GlobalAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """2000 req/h per IP — coarse global anonymous cap."""

    scope = "global_anon"
