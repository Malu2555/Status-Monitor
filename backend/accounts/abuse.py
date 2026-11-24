"""Application-level abuse controls: trusted IP parsing, honeypot, auto-block."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("accounts")

# Cross these thresholds and the IP is blocked automatically.
AUTO_BLOCK_WINDOW_SECONDS = 3600
AUTO_BLOCK_THRESHOLD = 50
AUTO_BLOCK_FOR_SECONDS = 24 * 3600


def client_ip(request) -> str:
    """Client IP, trusting ``X-Forwarded-For`` only from configured proxies.

    ``TRUSTED_PROXY_IPS=*`` trusts every peer — only appropriate when the app is
    always behind a managed proxy (Render, Fly, Cloudflare). ``PROXY_HOPS`` says
    how many trailing entries were appended by trusted proxies (1 = rightmost;
    set 2 for a Vercel → Render chain).
    """
    remote = request.META.get("REMOTE_ADDR", "") or ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    trusted = set(getattr(settings, "TRUSTED_PROXY_IPS", []) or [])
    if forwarded and (remote in trusted or "*" in trusted):
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            hops = max(int(getattr(settings, "PROXY_HOPS", 1) or 1), 1)
            return parts[-min(hops, len(parts))]
    return remote


def _login_failure_key(username: str) -> str:
    return f"login:fail:user:{(username or '').strip().lower()[:150]}"


def _login_lock_key(username: str) -> str:
    return f"login:lock:{(username or '').strip().lower()[:150]}"


def login_locked(username: str) -> bool:
    """True while a username is in the short lockout window."""
    if not username:
        return False
    try:
        return bool(cache.get(_login_lock_key(username)))
    except Exception:  # cache unavailable must not block logins
        return False


def note_login_failure(username: str) -> bool:
    """Count a credential failure per username; lock after the threshold."""
    if not username:
        return False
    window = getattr(settings, "LOGIN_LOCK_WINDOW", 900)
    threshold = getattr(settings, "LOGIN_MAX_FAILURES", 10)
    key = _login_failure_key(username)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    except Exception:
        return False
    if count >= threshold:
        try:
            cache.set(
                _login_lock_key(username),
                True,
                getattr(settings, "LOGIN_LOCK_SECONDS", 600),
            )
            cache.delete(key)
        except Exception:
            return False
        return True
    return False


def clear_login_failures(username: str) -> None:
    """Reset the per-username failure streak after a successful login."""
    try:
        cache.delete(_login_failure_key(username))
        cache.delete(_login_lock_key(username))
    except Exception:
        return


def blocked_ip(ip: str):
    """Return the live BlockedIP row for ``ip`` (deleting an expired one)."""
    from .models import BlockedIP

    if not ip:
        return None
    row = BlockedIP.objects.filter(ip=ip).first()
    if row is None:
        return None
    if row.is_expired():
        row.delete()
        return None
    return row


def block_ip(ip: str, reason: str = "", *, auto: bool = False, seconds: int | None = None):
    """Create or refresh a block. ``seconds=None`` means permanent."""
    from .models import BlockedIP

    if not ip:
        return None
    expires_at = timezone.now() + timedelta(seconds=seconds) if seconds else None
    row, _ = BlockedIP.objects.update_or_create(
        ip=ip,
        defaults={"reason": reason[:120], "auto": auto, "expires_at": expires_at},
    )
    logger.warning("ip blocked: ip=%s auto=%s reason=%s", ip, auto, reason)
    return row


def unblock_ip(ip: str) -> bool:
    from .models import BlockedIP

    deleted, _ = BlockedIP.objects.filter(ip=ip).delete()
    return bool(deleted)


def note_failure(ip: str, kind: str) -> bool:
    """Record a suspicious event; auto-block when the hourly threshold trips.

    Returns True when this call caused a block. Counting lives in the cache so
    it is shared across workers and needs no extra DB round-trip per request.
    """
    from .models import AbuseEvent

    AbuseEvent.objects.create(kind=kind, ip=ip or "")
    if not ip:
        return False

    window = int(getattr(settings, "AUTO_BLOCK_WINDOW_SECONDS", AUTO_BLOCK_WINDOW_SECONDS))
    threshold = int(getattr(settings, "AUTO_BLOCK_THRESHOLD", AUTO_BLOCK_THRESHOLD))
    block_for = int(getattr(settings, "AUTO_BLOCK_FOR_SECONDS", AUTO_BLOCK_FOR_SECONDS))

    key = f"abuse:fail:{ip}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1

    if count >= threshold:
        block_ip(
            ip,
            reason=f"auto: {count} {kind} events in 1h",
            auto=True,
            seconds=block_for,
        )
        cache.delete(key)
        return True
    return False
