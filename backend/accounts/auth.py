from ninja.security import HttpBearer

from .models import User
from .services import safe_decode_token, user_from_payload


class AuthBearer(HttpBearer):
    """Authenticates requests presenting a valid access JWT.

    Returns the ``User`` (becomes ``request.auth``) or ``None`` → 401.
    """

    def authenticate(self, request, token) -> "User | None":
        payload = safe_decode_token(token, "access")
        if payload is None:
            return None  # missing, expired, wrong type or bad signature
        return user_from_payload(payload)
