"""Postal alerts for security-relevant admin events (no-op if unset)."""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("accounts")


def notify_admin(subject: str, body: str) -> None:
    """Email ADMIN_ALERT_EMAIL; silently ignored when it is not configured."""
    recipient = getattr(settings, "ADMIN_ALERT_EMAIL", "") or ""
    if not recipient:
        return
    try:
        send_mail(
            f"[Status Monitor] {subject}",
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=True,
        )
    except Exception as exc:  # never let alerting break a login flow
        logger.warning("admin alert failed: %s", exc)
