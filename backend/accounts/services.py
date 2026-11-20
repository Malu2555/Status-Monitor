"""JWT issuance/validation, cookie helpers and refresh-token blacklist."""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime

import jwt
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone as dj_timezone

from .models import AccountActionToken, RevokedRefreshToken

ALGORITHM = "HS256"

logger = logging.getLogger("accounts")


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
        "email_verified": user.email_verified,
        "otp_enabled": user_otp_enabled(user),
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


# --------------------------------------------------------------------------
# Account lifecycle: verification + password reset tokens
# --------------------------------------------------------------------------
def issue_account_token(user, purpose: str) -> AccountActionToken:
    """Create a single-use token; supersedes any unspent token of the same purpose."""
    ttl = (
        settings.VERIFY_EMAIL_TOKEN_TTL
        if purpose == "verify_email"
        else settings.PASSWORD_RESET_TOKEN_TTL
    )
    AccountActionToken.objects.filter(user=user, purpose=purpose, consumed_at=None).delete()
    return AccountActionToken.objects.create(
        id=secrets.token_urlsafe(32),
        user=user,
        purpose=purpose,
        expires_at=dj_timezone.now() + ttl,
    )


def consume_account_token(token_id: str, purpose: str):
    """Redeem a token; returns the owning user or None when invalid/expired/used."""
    try:
        token = AccountActionToken.objects.select_related("user").get(
            id=token_id,
            purpose=purpose,
            consumed_at=None,
            expires_at__gt=dj_timezone.now(),
        )
    except AccountActionToken.DoesNotExist:
        return None
    token.consumed_at = dj_timezone.now()
    token.save(update_fields=["consumed_at"])
    return token.user


def send_verification_email(user) -> None:
    token = issue_account_token(user, "verify_email")
    link = f"{settings.FRONTEND_URL}/verify-email?token={token.id}"
    send_mail(
        "Verify your Status Monitor account",
        f"Hi {user.username},\n\nConfirm your email address:\n{link}\n\n"
        "This link expires in 24 hours. If you didn't create an account, "
        "you can ignore this email.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def send_password_reset_email(user) -> None:
    token = issue_account_token(user, "password_reset")
    link = f"{settings.FRONTEND_URL}/reset-password?token={token.id}"
    send_mail(
        "Reset your Status Monitor password",
        f"Hi {user.username},\n\nReset your password here:\n{link}\n\n"
        "This link expires in 1 hour. If you didn't request this reset, "
        "you can ignore this email.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


# --------------------------------------------------------------------------
# Two-factor authentication (opt-in TOTP via django-otp)
# --------------------------------------------------------------------------
def user_otp_enabled(user) -> bool:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def verify_otp_code(user, code: str) -> bool:
    if not code:
        return False
    from django_otp import match_token

    try:
        return match_token(user, code) is not None
    except Exception:
        return False


def create_totp_device(user):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device, _ = TOTPDevice.objects.get_or_create(
        user=user, name="default", defaults={"confirmed": False}
    )
    return device


def confirm_totp_device(user, code: str) -> bool:
    """Validate a code against the *unconfirmed* device and flip it to confirmed."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.filter(user=user, name="default", confirmed=False).first()
    if device is None or not device.verify_token(code):
        return False
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    return True


# --------------------------------------------------------------------------
# Two-factor recovery codes (single-use, stored hashed)
# --------------------------------------------------------------------------
RECOVERY_CODE_COUNT = 10


def _normalize_recovery_code(code: str) -> str:
    return (code or "").replace("-", "").replace(" ", "").upper()


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(_normalize_recovery_code(code).encode()).hexdigest()


def issue_recovery_codes(user, count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Replace the user's recovery codes; return the new plaintext codes once."""
    from .models import RecoveryCode

    RecoveryCode.objects.filter(user=user).delete()
    plaintext: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(8).upper()  # 16 hex chars
        RecoveryCode.objects.create(user=user, hashed_code=_hash_recovery_code(raw))
        plaintext.append("-".join(raw[i : i + 4] for i in range(0, len(raw), 4)))
    return plaintext


def recovery_codes_summary(user) -> dict:
    from .models import RecoveryCode

    queryset = RecoveryCode.objects.filter(user=user)
    return {
        "total": queryset.count(),
        "unused": queryset.filter(used_at__isnull=True).count(),
    }


def verify_otp_or_recovery(user, code: str) -> bool:
    """Accept either a current TOTP code or a single-use recovery code."""
    if not code:
        return False
    if verify_otp_code(user, code):
        return True
    normalized = _normalize_recovery_code(code)
    if len(normalized) != 16:
        return False
    from .models import RecoveryCode

    record = RecoveryCode.objects.filter(
        user=user, hashed_code=_hash_recovery_code(normalized), used_at__isnull=True
    ).first()
    if record is None:
        return False
    record.used_at = dj_timezone.now()
    record.save(update_fields=["used_at"])
    logger.info("recovery code consumed: user=%s", user.pk)
    return True


# --------------------------------------------------------------------------
# API tokens (programmatic access via the X-API-Key header)
# --------------------------------------------------------------------------
API_TOKEN_PREFIX = "sm_"


def hash_api_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_api_token(user, name: str, scope: str = "write"):
    """Create a token and return ``(plaintext, record)`` — plaintext shown once."""
    from .models import ApiToken

    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    record = ApiToken.objects.create(
        user=user,
        name=(name.strip()[:100] or "API token"),
        prefix=raw[:10],
        hashed_key=hash_api_token(raw),
        scope=scope if scope in ("read", "write") else "write",
    )
    return raw, record


def api_token_record(raw: str):
    """Return the live ApiToken for a plaintext key, or None."""
    from .models import ApiToken

    if not raw or not raw.startswith(API_TOKEN_PREFIX):
        return None
    try:
        record = ApiToken.objects.select_related("user").get(
            hashed_key=hash_api_token(raw), revoked_at__isnull=True
        )
    except ApiToken.DoesNotExist:
        return None
    if not record.user.is_active:
        return None
    now = dj_timezone.now()
    if record.last_used_at is None or (now - record.last_used_at).total_seconds() > 60:
        ApiToken.objects.filter(pk=record.pk).update(last_used_at=now)
    return record


# --------------------------------------------------------------------------
# Legal policies (terms / privacy / acceptable use)
# --------------------------------------------------------------------------
POLICY_SLUGS = ("terms", "privacy")


def current_policy(slug: str):
    """Latest published text for ``slug``, or None."""
    from .models import Policy

    return Policy.objects.filter(slug=slug).order_by("-effective_at", "-created_at").first()


def record_tos_acceptance(user):
    """Stamp proof-of-consent on the account (called once, at registration)."""
    now = dj_timezone.now()
    user.tos_accepted_at = now
    user.age_confirmed_at = now
    user.tos_version = settings.TOS_VERSION
    user.save(update_fields=["tos_accepted_at", "age_confirmed_at", "tos_version"])
    return user


# --------------------------------------------------------------------------
# Moderation: is_active=False is the kill switch (JWT + API keys both honour it)
# --------------------------------------------------------------------------
def disable_user(user, reason: str = "manual") -> int:
    """Deactivate an account and pause its monitors. Returns how many were paused."""
    from monitors.models import Monitor

    paused_ids = list(
        Monitor.objects.filter(owner=user, is_active=True).values_list("id", flat=True)
    )
    if paused_ids:
        Monitor.objects.filter(id__in=paused_ids).update(is_active=False)
    user.is_active = False
    user.disabled_reason = reason
    user.disabled_at = dj_timezone.now()
    user.paused_monitor_ids = paused_ids
    user.save(
        update_fields=[
            "is_active",
            "disabled_reason",
            "disabled_at",
            "paused_monitor_ids",
        ]
    )
    return len(paused_ids)


def enable_user(user) -> int:
    """Reactivate an account and resume only the monitors moderation paused."""
    from monitors.models import Monitor

    paused_ids = list(user.paused_monitor_ids or [])
    resumed = 0
    if paused_ids:
        resumed = Monitor.objects.filter(id__in=paused_ids, owner=user).update(is_active=True)
    user.is_active = True
    user.disabled_reason = ""
    user.disabled_at = None
    user.paused_monitor_ids = []
    user.save(
        update_fields=[
            "is_active",
            "disabled_reason",
            "disabled_at",
            "paused_monitor_ids",
        ]
    )
    return resumed


def is_staff(user) -> bool:
    """True when the authenticated principal may moderate other accounts."""
    return bool(user is not None and getattr(user, "is_staff", False))
