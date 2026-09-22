"""Audit helpers: append rows from any request/actor context, never raise."""
import logging

from .models import AuditLogEntry

logger = logging.getLogger("audit")


def client_ip(request) -> str:
    """Best-effort client IP (X-Forwarded-For aware)."""
    if request is None:
        return ""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def audit_log(request, kind: str, user=None, **payload):
    """Append an audit row; returns the row or None.

    Auditing must never break the main flow, so any failure is logged and
    swallowed. ``payload`` must be JSON-serializable and MUST NOT contain
    secrets (passwords, tokens, card data).
    """
    try:
        return AuditLogEntry.objects.create(
            user=user,
            kind=kind,
            payload=payload,
            ip=client_ip(request) or None,
        )
    except Exception:
        logger.exception("audit write failed: kind=%s", kind)
        return None
