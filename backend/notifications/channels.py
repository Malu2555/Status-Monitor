"""Channel dispatch: turn one NotificationDelivery into an outbound message."""
import logging

import httpx
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("notifications")

SUBJECTS = {
    "down": "⬇ {name} is DOWN",
    "up": "✅ {name} is back UP",
}


def _monitor_lines(row) -> list[str]:
    monitor = row.monitor
    details = row.payload or {}
    lines = [
        f"Monitor: {monitor.name}",
        f"URL: {monitor.url}",
        f"Event: {row.event_kind.upper()}",
    ]
    if details.get("status_code") is not None:
        lines.append(f"HTTP status: {details['status_code']}")
    if details.get("response_ms") is not None:
        lines.append(f"Latency: {details['response_ms']} ms")
    if details.get("error"):
        lines.append(f"Detail: {details['error']}")
    return lines


def _dispatch_email(address: str, row) -> None:
    subject = SUBJECTS[row.event_kind].format(name=row.monitor.name)
    send_mail(
        subject,
        "\n".join(_monitor_lines(row)),
        settings.DEFAULT_FROM_EMAIL,
        [address],
        fail_silently=False,
    )


def _dispatch_webhook(address: str, row) -> None:
    payload = {
        "event": row.event_kind,
        "monitor_id": row.monitor_id,
        "monitor_name": row.monitor.name,
        "monitor_url": row.monitor.url,
        **(row.payload or {}),
    }
    with httpx.Client(timeout=10) as client:
        response = client.post(
            address,
            json=payload,
            headers={"User-Agent": "StatusMonitor/1.0"},
        )
        response.raise_for_status()


def dispatch(channel, row) -> None:
    """Send one delivery through its channel; raises on failure."""
    if channel.kind == "email":
        _dispatch_email(channel.address, row)
    elif channel.kind == "webhook":
        _dispatch_webhook(channel.address, row)
    else:
        raise ValueError(f"unsupported notification channel kind: {channel.kind!r}")
