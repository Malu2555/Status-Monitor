"""Check engine: SSRF-safe fetching, uptime stats, due-check logic."""

import ipaddress
import logging
import socket
import time
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import httpx
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import Check, Monitor

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


def run_check(monitor: Monitor) -> dict:
    """Probe one monitor, persist a Check row and refresh cached status.

    Redirects are followed manually (max CHECK_MAX_REDIRECTS) with full SSRF
    re-validation on every hop.
    """
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
    Check.objects.create(
        monitor=monitor,
        is_up=is_up,
        status_code=status_code,
        response_ms=response_ms,
        error=error,
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
