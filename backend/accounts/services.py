"""JWT issuance/validation, cookie helpers and refresh-token blacklist."""

import secrets
import uuid
from datetime import UTC, datetime

import jwt
from django.conf import settings
from django.utils import timezone as dj_timezone

from .models import RevokedRefreshToken

ALGORITHM = "HS256"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_access_token(user) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user.pk),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + settings.ACCESS_TOKEN_LIFETIME,
    }
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)


def create_refresh_token(user) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user.pk),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + settings.REFRESH_TOKEN_LIFETIME,
    }
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    payload = jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def safe_decode_token(token: str, expected_type: str) -> "dict | None":
    """Decode a JWT without raising; None means missing/expired/bad signature/type.

    Single choke point for the different failures PyJWT can raise so callers
    never need a blind ``except Exception``.
    """
    try:
        return decode_token(token, expected_type)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def user_from_payload(payload: dict):
    from .models import User

    try:
        return User.objects.get(pk=int(payload["sub"]), is_active=True)
    except (User.DoesNotExist, KeyError, TypeError, ValueError):
        return None


def issue_token_pair(user):
    return create_access_token(user), create_refresh_token(user)


def user_dict(user) -> dict:
    """Serializable user + plan info (shared by /me and token responses)."""
    from billing.services import get_plan_summary

    info = get_plan_summary(user)
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "plan": info["plan"],
        "plan_label": info["label"],
        "monitors_used": info["monitors_used"],
        "monitors_limit": info["monitors_limit"],
        "subscription_status": info["subscription_status"],
    }


def token_response(user, access: str) -> dict:
    return {
        "access": access,
        "token_type": "Bearer",
        "expires_in": int(settings.ACCESS_TOKEN_LIFETIME.total_seconds()),
        "user": user_dict(user),
    }


# --------------------------------------------------------------------------
# Cookies
# --------------------------------------------------------------------------
def set_refresh_cookie(response, refresh_token: str) -> None:
    response.set_cookie(
        settings.COOKIE_REFRESH_NAME,
        refresh_token,
        max_age=int(settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="Strict",
        path="/api/auth",
    )


def set_csrf_cookie(response) -> str:
    """Readable cookie for the CSRF double-submit pattern on /auth/refresh."""
    value = secrets.token_urlsafe(32)
    response.set_cookie(
        settings.COOKIE_CSRF_NAME,
        value,
        max_age=int(settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="Strict",
        path="/",
    )
    return value


def clear_app_cookies(response) -> None:
    response.delete_cookie(settings.COOKIE_REFRESH_NAME, path="/api/auth")
    response.delete_cookie(settings.COOKIE_CSRF_NAME, path="/")


# --------------------------------------------------------------------------
# Blacklist (logout + rotation reuse detection)
# --------------------------------------------------------------------------
def revoke_refresh_token(token: str) -> None:
    payload = safe_decode_token(token, "refresh")
    if payload is None:
        return  # malformed/expired tokens have nothing left to revoke
    RevokedRefreshToken.objects.get_or_create(
        jti=payload["jti"],
        defaults={
            "expires_at": datetime.fromtimestamp(payload["exp"], tz=UTC),
            "user_id": payload.get("sub"),
        },
    )


def is_refresh_revoked(token: str) -> bool:
    payload = safe_decode_token(token, "refresh")
    if payload is None:
        return True  # undecodable tokens must never be accepted
    return RevokedRefreshToken.objects.filter(jti=payload["jti"]).exists()


def prune_blacklist() -> None:
    RevokedRefreshToken.objects.filter(expires_at__lt=dj_timezone.now()).delete()
