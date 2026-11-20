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
    """Client IP, trusting ``X-Forwarded-For`` only from configured proxies."""
    remote = request.META.get("REMOTE_ADDR", "") or ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    trusted = set(getattr(settings, "TRUSTED_PROXY_IPS", []) or [])
    if forwarded and remote in trusted:
        return forwarded.split(",")[0].strip()
    return remote


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

    key = f"abuse:fail:{ip}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, AUTO_BLOCK_WINDOW_SECONDS)
        count = 1

    if count >= AUTO_BLOCK_THRESHOLD:
        block_ip(
            ip,
            reason=f"auto: {count} {kind} events in 1h",
            auto=True,
            seconds=AUTO_BLOCK_FOR_SECONDS,
        )
        cache.delete(key)
        return True
    return False
