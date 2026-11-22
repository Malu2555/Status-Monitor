"""Notification outbox: enqueue on monitor state transitions, deliver via channels."""

import logging

from django.db import transaction
from django.utils import timezone

from .models import MonitorNotificationChannel, NotificationDelivery

logger = logging.getLogger("notifications")


def enqueue_state_transition(monitor, previous_status: str, new_status: str, check_info: dict | None = None) -> int:
    """Queue one delivery per enabled channel when a monitor changes state.

    A first-ever successful check (unknown → up) is deliberately silent, and
    identical consecutive statuses enqueue nothing. Returns the number of
    deliveries enqueued.
    """
    if previous_status == new_status:
        return 0
    if previous_status == "unknown" and new_status == "up":
        logger.info("notifications: first check OK for monitor=%s — not alerting", monitor.pk)
        return 0
    channels = list(MonitorNotificationChannel.objects.filter(monitor=monitor, enabled=True))
    if not channels:
        return 0
    info = check_info or {}
    event_kind = "down" if new_status == "down" else "up"
    NotificationDelivery.objects.bulk_create(
        [
            NotificationDelivery(
                monitor=monitor,
                channel=channel,
                event_kind=event_kind,
                payload={
                    "previous_status": previous_status,
                    "new_status": new_status,
                    "status_code": info.get("status_code"),
                    "response_ms": info.get("response_ms"),
                    "error": (info.get("error") or "")[:200],
                },
            )
            for channel in channels
        ]
    )
    logger.info(
        "notifications enqueued: monitor=%s name=%s event=%s channels=%d",
        monitor.pk,
        monitor.name,
        event_kind,
        len(channels),
    )
    return len(channels)


def deliver_pending(batch: int = 50, max_attempts: int = 8) -> tuple[int, int, int]:
    """Attempt delivery of up to ``batch`` pending rows; returns (sent, failed, dead).

    Rows are claimed FOR UPDATE inside one transaction so two overlapping
    cron runs can never double-send; a failed delivery stays pending for the
    next pass and is dead-lettered after ``max_attempts``.
    """
    from .channels import dispatch

    with transaction.atomic():
        rows = list(
            NotificationDelivery.objects.select_for_update()
            .filter(status="pending")
            .select_related("channel", "monitor")
            .order_by("created_at")[:batch]
        )
        sent = failed = dead = 0
        for row in rows:
            row.attempts += 1
            try:
                dispatch(row.channel, row)
            except Exception as exc:
                row.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                if row.attempts >= max_attempts:
                    row.status = NotificationDelivery.Status.DEAD
                    dead += 1
                else:
                    failed += 1
            else:
                row.status = NotificationDelivery.Status.SENT
                row.sent_at = timezone.now()
                sent += 1
            row.save(update_fields=["attempts", "status", "last_error", "sent_at"])
    logger.info("notification delivery pass: sent=%d failed=%d dead=%d", sent, failed, dead)
    return sent, failed, dead


def enqueue_domain_alert(monitor, days_remaining: int, level: str) -> int:
    """Queue one domain-expiry alert per enabled channel.

    Like the TLS sweep, the caller only invokes this when the alert level
    changes so customers aren't reminded every day.
    """
    channels = list(MonitorNotificationChannel.objects.filter(monitor=monitor, enabled=True))
    if not channels:
        return 0
    NotificationDelivery.objects.bulk_create(
        [
            NotificationDelivery(
                monitor=monitor,
                channel=channel,
                event_kind="domain",
                payload={"days_remaining": days_remaining, "level": level},
            )
            for channel in channels
        ]
    )
    logger.info(
        "notifications enqueued: monitor=%s domain level=%s days=%s channels=%d",
        monitor.pk,
        level,
        days_remaining,
        len(channels),
    )
    return len(channels)


def enqueue_broken_links_alert(monitor, count: int, samples: list[dict]) -> int:
    """Queue one 'new broken links' alert per enabled channel."""
    channels = list(MonitorNotificationChannel.objects.filter(monitor=monitor, enabled=True))
    if not channels:
        return 0
    NotificationDelivery.objects.bulk_create(
        [
            NotificationDelivery(
                monitor=monitor,
                channel=channel,
                event_kind="broken_links",
                payload={"count": count, "samples": samples[:5]},
            )
            for channel in channels
        ]
    )
    logger.info(
        "notifications enqueued: monitor=%s broken_links=%s channels=%d",
        monitor.pk,
        count,
        len(channels),
    )
    return len(channels)


def enqueue_ssl_alert(monitor, days_remaining: int, level: str) -> int:
    """Queue one TLS-expiry alert per enabled channel.

    Escalation/dedupe (only alert when the level crosses a threshold) is the
    caller's responsibility — see the ``check_ssl`` management command.
    """
    channels = list(MonitorNotificationChannel.objects.filter(monitor=monitor, enabled=True))
    if not channels:
        return 0
    NotificationDelivery.objects.bulk_create(
        [
            NotificationDelivery(
                monitor=monitor,
                channel=channel,
                event_kind="ssl",
                payload={"days_remaining": days_remaining, "level": level},
            )
            for channel in channels
        ]
    )
    logger.info(
        "notifications enqueued: monitor=%s ssl level=%s days=%s channels=%d",
        monitor.pk,
        level,
        days_remaining,
        len(channels),
    )
    return len(channels)
