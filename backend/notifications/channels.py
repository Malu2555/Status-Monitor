"""Channel dispatch: turn one NotificationDelivery into an outbound message.

Supported kinds: email, generic webhook, Slack incoming webhook, Discord
webhook, and Telegram (address format ``bot_token|chat_id``).
"""
import logging

import httpx
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("notifications")

SUBJECTS = {
    "down": "⬇ {name} is DOWN",
    "up": "✅ {name} is back UP",
}


def _subject(row) -> str:
    if row.event_kind == "ssl":
        details = row.payload or {}
        level = details.get("level", "warn")
        icon = "🚨" if level == "critical" else "🔒"
        return f"{icon} {row.monitor.name} TLS expires in {details.get('days_remaining')} day(s)"
    return SUBJECTS.get(row.event_kind, "{name} status change").format(name=row.monitor.name)


def _monitor_lines(row) -> list[str]:
    monitor = row.monitor
    details = row.payload or {}
    lines = [
        f"Monitor: {monitor.name}",
        f"URL: {monitor.url}",
        f"Event: {row.event_kind.upper()}",
    ]
    if row.event_kind == "ssl":
        lines.append(
            f"TLS certificate expires in {details.get('days_remaining')} day(s) "
            f"(level: {details.get('level', 'warn')})"
        )
        return lines
    if details.get("status_code") is not None:
        lines.append(f"HTTP status: {details['status_code']}")
    if details.get("response_ms") is not None:
        lines.append(f"Latency: {details['response_ms']} ms")
    if details.get("error"):
        lines.append(f"Detail: {details['error']}")
    return lines


def _text(row) -> str:
    return f"{_subject(row)}\n" + "\n".join(_monitor_lines(row))


def _dispatch_email(address: str, row) -> None:
    send_mail(
        _subject(row),
        _text(row),
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


def _dispatch_slack(address: str, row) -> None:
    with httpx.Client(timeout=10) as client:
        response = client.post(address, json={"text": _text(row)})
        response.raise_for_status()


def _dispatch_discord(address: str, row) -> None:
    with httpx.Client(timeout=10) as client:
        response = client.post(address, json={"content": _text(row)})
        response.raise_for_status()


def _dispatch_telegram(address: str, row) -> None:
    """Telegram: ``address`` is ``bot_token|chat_id`` (tokens contain colons)."""
    token, _, chat_id = address.partition("|")
    if not token or not chat_id:
        raise ValueError("Telegram channel address must be 'bot_token|chat_id'.")
    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": _text(row), "disable_web_page_preview": True},
        )
        response.raise_for_status()


_HANDLERS = {
    "email": _dispatch_email,
    "webhook": _dispatch_webhook,
    "slack": _dispatch_slack,
    "discord": _dispatch_discord,
    "telegram": _dispatch_telegram,
}


def dispatch(channel, row) -> None:
    """Send one delivery through its channel; raises on failure."""
    handler = _HANDLERS.get(channel.kind)
    if handler is None:
        raise ValueError(f"unsupported notification channel kind: {channel.kind!r}")
    handler(channel.address, row)
