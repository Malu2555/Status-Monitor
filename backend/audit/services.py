"""Audit helpers: append rows from any request/actor context, never raise."""

import logging

from .models import AuditLogEntry

logger = logging.getLogger("audit")


def client_ip(request) -> str:
    """Best-effort client IP (trusted-proxy aware, consistent with rate limits)."""
    if request is None:
        return ""
    from accounts.abuse import client_ip as abuse_client_ip

    return abuse_client_ip(request)


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
