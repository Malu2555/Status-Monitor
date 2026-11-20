"""Check engine: SSRF-safe fetching, uptime stats, due-check logic."""

import ipaddress
import logging
import socket
import ssl
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlparse

import httpx
from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Check, Incident, MaintenanceWindow, Monitor, SslCertificate

logger = logging.getLogger("monitors")


def validate_target_url(url: str) -> str:
    """Validate a URL is fetchable and not routed to private space (SSRF guard).

    Rules: http/https only; hostname must resolve and every resolved address
    must be globally routable (private, loopback, link-local, reserved and
    multicast ranges are rejected).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise ValueError("The URL must include a hostname.")
    host = host.strip("[]")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ValueError("The hostname could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(
                "URLs pointing to private, loopback or internal networks are not allowed."
            )
    return parsed.geturl()


def should_check(monitor: Monitor) -> bool:
    if not monitor.last_checked_at:
        return True
    elapsed = timezone.now() - monitor.last_checked_at
    return elapsed.total_seconds() >= monitor.check_interval_seconds


def run_check(monitor: Monitor, region: str | None = None) -> dict:
    """Probe one monitor, persist a Check row and refresh cached status.

    Redirects are followed manually (max CHECK_MAX_REDIRECTS) with full SSRF
    re-validation on every hop. ``region`` stamps the probe so multiple runners
    can report independently.
    """
    region = region or settings.REGION_NAME
    started = time.monotonic()
    status_code = None
    is_up = False
    error = ""
    try:
        with httpx.Client(
            timeout=settings.CHECK_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            current = monitor.url
            for _ in range(settings.CHECK_MAX_REDIRECTS + 1):
                current = validate_target_url(current)
                response = client.get(
                    current, headers={"User-Agent": "StatusMonitor/1.0", "Accept": "*/*"}
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if location:
                        current = urljoin(current, location)
                        continue
                status_code = response.status_code
                break
        is_up = status_code is not None and 200 <= status_code < 400
        if status_code is not None and not is_up:
            error = f"HTTP {status_code}"
    except (httpx.HTTPError, ValueError, OSError) as exc:
        # Timeouts + TLS/DNS failures (httpx/OSError) and SSRF rejections (ValueError).
        error = str(exc)[:400]
        is_up = False

    response_ms = int((time.monotonic() - started) * 1000)
    previous_status = monitor.last_status
    Check.objects.create(
        monitor=monitor,
        is_up=is_up,
        status_code=status_code,
        response_ms=response_ms,
        error=error,
        region=region,
    )
    monitor.last_status = Monitor.Status.UP if is_up else Monitor.Status.DOWN
    monitor.last_status_code = status_code
    monitor.last_response_ms = response_ms
    monitor.last_checked_at = timezone.now()
    monitor.save(
        update_fields=[
            "last_status",
            "last_status_code",
            "last_response_ms",
            "last_checked_at",
            "updated_at",
        ]
    )
    logger.info(
        "check: monitor=%s name=%s ok=%s code=%s ms=%s error=%s",
        monitor.pk,
        monitor.name,
        is_up,
        status_code,
        response_ms,
        error[:80],
    )
    now = timezone.now()
    if previous_status != monitor.last_status:
        # Track outage windows: open on down transition, close on recovery.
        if monitor.last_status == Monitor.Status.DOWN:
            Incident.objects.create(
                monitor=monitor, started_at=now, last_status_code=status_code
            )
        else:
            Incident.objects.filter(monitor=monitor, ended_at=None).update(ended_at=now)
        if monitor.last_status == Monitor.Status.DOWN and MaintenanceWindow.objects.filter(
            monitor=monitor, starts_at__lte=now, ends_at__gte=now
        ).exists():
            logger.info("check: monitor=%s down during maintenance — alert suppressed", monitor.pk)
        else:
            from notifications.services import enqueue_state_transition

            enqueue_state_transition(
                monitor,
                previous_status,
                monitor.last_status,
                {"status_code": status_code, "response_ms": response_ms, "error": error},
            )
    elif not is_up:
        # Still down (no status change): keep the open incident current.
        Incident.objects.filter(monitor=monitor, ended_at=None).update(
            checks_down=F("checks_down") + 1, last_status_code=status_code
        )
    return {"is_up": is_up, "status_code": status_code, "response_ms": response_ms, "error": error}


def uptime_stats(monitor: Monitor, hours: int = 24) -> dict:
    """Percentages + per-hour buckets for the last ``hours``."""
    cutoff = timezone.now() - timedelta(hours=hours)
    checks = list(
        Check.objects.filter(monitor=monitor, checked_at__gte=cutoff).order_by("checked_at")
    )
    total = len(checks)
    up_count = sum(1 for check in checks if check.is_up)

    buckets: dict = {}
    for check in checks:
        key = timezone.localtime(check.checked_at).replace(minute=0, second=0, microsecond=0)
        info = buckets.setdefault(key, {"up": 0, "samples": 0})
        info["samples"] += 1
        if check.is_up:
            info["up"] += 1

    series = []
    if buckets:
        cursor = min(buckets)
        end = max(buckets)
        while cursor <= end:
            info = buckets.get(cursor, {"up": 0, "samples": 0})
            ratio = round(info["up"] / info["samples"], 3) if info["samples"] else 0.0
            series.append(
                {"bucket": cursor.isoformat(), "up_ratio": ratio, "samples": info["samples"]}
            )
            cursor += timedelta(hours=1)

    return {
        "uptime_percent": round(up_count / total * 100, 2) if total else None,
        "total_checks": total,
        "up_checks": up_count,
        "series": series,
    }


def bulk_uptime(monitor_ids: list[int], hours: int = 24) -> dict:
    """{monitor_id: uptime_percent} over the last ``hours`` in one query."""
    if not monitor_ids:
        return {}
    cutoff = timezone.now() - timedelta(hours=hours)
    rows = (
        Check.objects.filter(monitor_id__in=monitor_ids, checked_at__gte=cutoff)
        .values("monitor_id")
        .annotate(total=Count("id"), up=Count("id", filter=Q(is_up=True)))
    )
    return {
        row["monitor_id"]: (round(row["up"] / row["total"] * 100, 2) if row["total"] else None)
        for row in rows
    }


# --------------------------------------------------------------------------
# TLS certificate expiry monitoring
# --------------------------------------------------------------------------
def _host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("TLS checks require an https:// URL.")
    host = (parsed.hostname or "").strip("[]")
    if not host:
        raise ValueError("The URL must include a hostname.")
    return host, parsed.port or 443


def _cert_name(name) -> str:
    if not name or not isinstance(name, (tuple, list)):
        return ""
    values = [value for rdn in name for key, value in rdn if key == "commonName"]
    return ", ".join(values)


def _cert_time(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(value), tz=UTC)
    except (ValueError, TypeError):
        return None


def check_ssl(monitor: Monitor) -> dict:
    """Fetch the TLS certificate for an https monitor and persist its expiry.

    Reuses the SSRF guard from ``validate_target_url`` so we never connect to
    private address space.
    """
    validate_target_url(monitor.url)
    host, port = _host_port(monitor.url)
    subject = issuer = ""
    not_before = not_after = None
    days_remaining = None
    error = ""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=settings.CHECK_TIMEOUT_SECONDS) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
        subject = _cert_name(cert.get("subject"))
        issuer = _cert_name(cert.get("issuer"))
        not_before = _cert_time(cert.get("notBefore"))
        not_after = _cert_time(cert.get("notAfter"))
        if not_after is not None:
            days_remaining = (not_after - datetime.now(UTC)).days
    except (ssl.SSLError, OSError, ValueError) as exc:
        error = str(exc)[:400]

    record, _ = SslCertificate.objects.update_or_create(
        monitor=monitor,
        defaults={
            "subject": subject,
            "issuer": issuer,
            "not_before": not_before,
            "not_after": not_after,
            "days_remaining": days_remaining,
            "error": error,
        },
    )
    return {
        "subject": subject,
        "issuer": issuer,
        "not_before": not_before,
        "not_after": not_after,
        "days_remaining": days_remaining,
        "error": error,
        "alert_level": record.alert_level,
    }


def regional_statuses(monitor: Monitor, hours: int = 24) -> list[dict]:
    """Latest probe per region plus uptime over ``hours`` (multi-region view)."""
    cutoff = timezone.now() - timedelta(hours=hours)
    checks = Check.objects.filter(monitor=monitor, checked_at__gte=cutoff).order_by(
        "region", "-checked_at"
    )
    per_region: dict[str, dict] = {}
    for check in checks:
        entry = per_region.setdefault(
            check.region, {"total": 0, "up": 0, "latest": check}
        )
        entry["total"] += 1
        if check.is_up:
            entry["up"] += 1
    result = []
    for region, entry in sorted(per_region.items()):
        latest = entry["latest"]
        result.append(
            {
                "region": region,
                "last_status": "up" if latest.is_up else "down",
                "last_checked_at": latest.checked_at,
                "last_response_ms": latest.response_ms,
                "uptime_percent": (
                    round(entry["up"] / entry["total"] * 100, 2) if entry["total"] else None
                ),
            }
        )
    return result


# --------------------------------------------------------------------------
# Heartbeat (cron-job) monitors
# --------------------------------------------------------------------------
def record_heartbeat_ping(monitor: Monitor) -> dict:
    """Record an inbound ping; flip a down monitor back to up."""
    now = timezone.now()
    previous = monitor.last_status
    monitor.last_ping_at = now
    monitor.last_checked_at = now
    monitor.last_status = Monitor.Status.UP
    monitor.save(update_fields=["last_ping_at", "last_checked_at", "last_status", "updated_at"])
    Check.objects.create(
        monitor=monitor, is_up=True, error="heartbeat", region=settings.REGION_NAME
    )
    if previous == Monitor.Status.DOWN:
        Incident.objects.filter(monitor=monitor, ended_at=None).update(ended_at=now)
        from notifications.services import enqueue_state_transition

        enqueue_state_transition(
            monitor, previous, Monitor.Status.UP, {"error": "heartbeat resumed"}
        )
        logger.info("heartbeat resumed: monitor=%s", monitor.pk)
    return {"is_up": True, "status_code": None, "response_ms": None, "error": "heartbeat"}


def evaluate_heartbeat(monitor: Monitor) -> dict:
    """Mark a heartbeat monitor down when no ping arrived within interval+grace."""
    now = timezone.now()
    last = monitor.last_ping_at or monitor.created_at
    deadline = last + timedelta(
        seconds=monitor.check_interval_seconds + monitor.heartbeat_grace_seconds
    )
    if now <= deadline:
        return {"is_up": True, "status_code": None, "response_ms": None, "error": "heartbeat ok"}

    if monitor.last_status != Monitor.Status.DOWN:
        previous = monitor.last_status
        monitor.last_status = Monitor.Status.DOWN
        monitor.last_checked_at = now
        monitor.save(update_fields=["last_status", "last_checked_at", "updated_at"])
        Check.objects.create(
            monitor=monitor, is_up=False, error="heartbeat missed", region=settings.REGION_NAME
        )
        Incident.objects.create(monitor=monitor, started_at=now)
        suppressed = MaintenanceWindow.objects.filter(
            monitor=monitor, starts_at__lte=now, ends_at__gte=now
        ).exists()
        if not suppressed:
            from notifications.services import enqueue_state_transition

            enqueue_state_transition(
                monitor, previous, Monitor.Status.DOWN, {"error": "heartbeat missed"}
            )
        logger.warning("heartbeat missed: monitor=%s", monitor.pk)
    return {"is_up": False, "status_code": None, "response_ms": None, "error": "heartbeat missed"}


# --------------------------------------------------------------------------
# Incident postmortem drafts (deterministic — no external AI dependency)
# --------------------------------------------------------------------------
def draft_postmortem(incident: Incident) -> str:
    """Build a customer-facing postmortem draft from the incident timeline."""
    monitor = incident.monitor
    ended = incident.ended_at or timezone.now()
    minutes = max(1, int((ended - incident.started_at).total_seconds() // 60))
    lines = [
        f"## Incident summary — {monitor.name}",
        "",
        f"Status: {'resolved' if incident.ended_at else 'ongoing'}",
        f"Started: {incident.started_at:%Y-%m-%d %H:%M} UTC",
        f"Resolved: {incident.ended_at:%Y-%m-%d %H:%M} UTC" if incident.ended_at else "Resolved: —",
        f"Duration: ~{minutes} minute(s)",
        f"Failed checks: {incident.checks_down}",
    ]
    if incident.last_status_code:
        lines.append(f"Last HTTP status: {incident.last_status_code}")
    lines += [
        "",
        "### What happened",
        f"{monitor.name} ({monitor.url}) stopped responding as expected and our monitor "
        f"recorded {incident.checks_down} consecutive failed check(s).",
        "",
        "### Impact",
        f"Availability of {monitor.name} was affected for approximately {minutes} minute(s).",
        "",
        "### Next steps",
        "- Confirm the service is fully healthy (see the live status above).",
        "- Add a follow-up note here with the root cause and prevention.",
    ]
    return "\n".join(lines)
