"""Security hardening headers + application-level IP blocking."""

from django.http import JsonResponse


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
        return response


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
