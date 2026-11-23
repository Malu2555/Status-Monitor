"""Security hardening headers + application-level IP blocking."""

import ipaddress

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


class SecurityHeadersMiddleware:
    """Adds CSP and friends. CSP is restrictive by design; loosen in prod if needed."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if response.status_code == 429:
            response.setdefault("Retry-After", "60")
        # Public feed reads are safe to cache at the edge (Vercel/Render).
        if request.method == "GET" and request.path.startswith("/api/public/") and response.status_code == 200:
            response.setdefault("Cache-Control", "public, max-age=15, s-maxage=30, stale-while-revalidate=60")
        return response


def _ip_allowed(ip: str, allowlist: list[str]) -> bool:
    """True when ``ip`` matches the allow-list ("*" allows every peer)."""
    if not allowlist or "*" in allowlist:
        return True
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if "/" in entry:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            elif address == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


class AdminGuardMiddleware:
    """Gate the admin prefix by IP allow-list and a coarse per-IP request cap.

    Runs before routing; denied requests get a plain 404 so the admin path is
    indistinguishable from a non-existent URL.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_path = getattr(settings, "ADMIN_PATH", "/admin/")
        if not settings.ADMIN_ENABLED or not request.path.startswith(admin_path):
            return self.get_response(request)

        from accounts.abuse import client_ip

        ip = client_ip(request)
        if not _ip_allowed(ip, getattr(settings, "ADMIN_IP_ALLOWLIST", [])):
            return HttpResponse(status=404)

        limit = getattr(settings, "ADMIN_RATE_LIMIT_PER_MIN", 0)
        if limit:
            from django.utils import timezone

            minute = timezone.now().strftime("%Y%m%d%H%M")
            key = f"admin:req:{ip}:{minute}"
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, 90)
                count = 1
            except Exception:
                return self.get_response(request)
            if count > limit:
                return HttpResponse(status=429)

        return self.get_response(request)


class BlockedIPMiddleware:
    """Answer 403 before routing for IPs in the BlockedIP table.

    OPTIONS is exempt so legitimate browsers can still complete CORS preflight
    when the frontend is served from another origin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != "OPTIONS":
            from accounts.abuse import blocked_ip, client_ip

            if blocked_ip(client_ip(request)) is not None:
                response = JsonResponse({"detail": "Access denied."}, status=403)
                response["Content-Type"] = "application/json"
                return response
        return self.get_response(request)
