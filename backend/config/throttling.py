"""Rate-limit classes with isolated cache buckets.

django-ninja's throttles bucket by `scope` only (the rate string is not part
of the cache key), so every distinct rate needs its own scope/subclass —
otherwise two rates would silently share one bucket.
"""

from django.conf import settings
from ninja.throttling import AnonRateThrottle, AuthRateThrottle, BaseThrottle


class _TestAwareThrottle(BaseThrottle):
    """Skips throttling in tests, and lets global envelopes ignore hot paths."""

    #: Global envelope throttles should not cap refresh probes (cookie + CSRF
    #: protected) or health checks; route-specific throttles still apply.
    skip_global_paths = False

    def allow_request(self, request):
        if getattr(settings, "DISABLE_THROTTLING", False):
            return True
        if self.skip_global_paths and request.path in (
            "/api/health",
            "/api/auth/refresh",
        ):
            return True
        return super().allow_request(request)

    def get_ident(self, request):
        """Use the same trusted-proxy IP logic as rate limiting/auto-blocking.

        django-ninja's default trusts (or concatenates) X-Forwarded-For, which
        is spoofable and collapses to one bucket behind a managed proxy.
        """
        from accounts.abuse import client_ip

        return client_ip(request) or "unknown"


class AuthAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """5 req/min per IP — registration, verification, password reset."""

    scope = "auth_anon"


class LoginAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """10 req/min per IP for login (per-username lockout adds depth)."""

    scope = "auth_login"


class RefreshAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """60 req/min per IP for refresh; avoids the shared-NAT lockout of 5/min."""

    scope = "auth_refresh"


class SessionAuthThrottle(_TestAwareThrottle, AuthRateThrottle):
    """Per-user limit for lightweight session endpoints (me/logout)."""

    scope = "session_auth"


class PublicAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """60 req/min per IP — free public status feed + Polar billing webhook."""

    scope = "public_anon"


class IpEnvelopeThrottle(_TestAwareThrottle, AnonRateThrottle):
    """Coarse per-IP envelope across every route (1500/h).

    Stacks on top of the per-route throttles so an attacker rotating usernames
    or hammering cheap endpoints still hits a wall, while a busy NAT with a
    handful of active users stays comfortably under the cap.
    """

    scope = "ip_envelope"
    skip_global_paths = True


class AdminJobThrottle(_TestAwareThrottle, AuthRateThrottle):
    """Per-user limit for the operator cron triggers.

    Separate scope from session_auth: the scheduler legitimately calls these 60
    times an hour (once a minute), while still capping abuse at 2/min.
    """

    scope = "admin_job"


class SchedulerThrottle(_TestAwareThrottle, AnonRateThrottle):
    """Machine-to-machine scheduler endpoint (X-Scheduler-Token).

    Bucketed by client IP; a single container/Worker calls it every minute, so
    the cap is high enough for 60s cadence but still bounds a leaked token.
    """

    scope = "admin_scheduler"


class MonitorAuthThrottle(_TestAwareThrottle, AuthRateThrottle):
    """Per-user limit for monitor CRUD and billing endpoints."""

    scope = "monitor_auth"


class GlobalAnonThrottle(_TestAwareThrottle, AnonRateThrottle):
    """2000 req/h per IP — coarse global anonymous cap."""

    scope = "global_anon"
    skip_global_paths = True
