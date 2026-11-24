from ninja.security import APIKeyHeader, HttpBearer

from .models import User
from .services import api_token_record, safe_decode_token, user_from_payload


class AuthBearer(HttpBearer):
    """Authenticates requests presenting a valid access JWT.

    Returns the ``User`` (becomes ``request.auth``) or ``None`` → 401.
    """

    def authenticate(self, request, token) -> "User | None":
        payload = safe_decode_token(token, "access")
        if payload is None:
            return None  # missing, expired, wrong type or bad signature
        return user_from_payload(payload)


class ApiKeyAuth(APIKeyHeader):
    """Authenticates requests presenting an ``X-API-Key`` token.

    Exposes the token scope on ``request.api_token_scope`` so write endpoints
    can reject read-only tokens. Returns the owning ``User`` (like JWT auth).
    """

    param_name = "X-API-Key"

    def authenticate(self, request, key) -> "User | None":
        if not key:
            return None
        record = api_token_record(key)
        if record is None:
            return None
        request.api_token_scope = record.scope  # type: ignore[attr-defined]
        return record.user
