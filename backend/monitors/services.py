"""Check engine: SSRF-safe fetching, uptime stats, due-check logic."""

import ipaddress
import logging
import re
import socket
import ssl
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlparse

import httpx
from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Check, DomainRegistration, Incident, MaintenanceWindow, Monitor, SslCertificate

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
            raise ValueError("URLs pointing to private, loopback or internal networks are not allowed.")
    return parsed.geturl()


def should_check(monitor: Monitor) -> bool:
    if not monitor.last_checked_at:
        return True
    elapsed = timezone.now() - monitor.last_checked_at
    return elapsed.total_seconds() >= monitor.check_interval_seconds


def record_check_result(
    monitor: Monitor,
    *,
    is_up: bool,
    status_code: int | None = None,
    response_ms: int | None = None,
    error: str = "",
    region: str | None = None,
    detail: dict | None = None,
) -> dict:
    """Persist one probe result, refresh cached state, and enqueue alerts.

    Shared by HTTP/keyword probes and the daily domain/broken-link sweeps so a
    down transition always opens an incident and a recovery always closes it.
    """
    region = region or settings.REGION_NAME
    previous_status = monitor.last_status
    Check.objects.create(
        monitor=monitor,
        is_up=is_up,
        status_code=status_code,
        response_ms=response_ms,
        error=error,
        detail=detail or {},
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
            Incident.objects.create(monitor=monitor, started_at=now, last_status_code=status_code)
        else:
            Incident.objects.filter(monitor=monitor, ended_at=None).update(ended_at=now)
        if (
            monitor.last_status == Monitor.Status.DOWN
            and MaintenanceWindow.objects.filter(monitor=monitor, starts_at__lte=now, ends_at__gte=now).exists()
        ):
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
    return {
        "is_up": is_up,
        "status_code": status_code,
        "response_ms": response_ms,
        "error": error,
        "detail": detail or {},
    }


def run_check(monitor: Monitor, region: str | None = None) -> dict:
    """Probe one HTTP or keyword monitor and persist the result.

    Redirects are followed manually (max CHECK_MAX_REDIRECTS) with full SSRF
    re-validation on every hop. ``region`` stamps the probe so multiple runners
    can report independently.
    """
    region = region or settings.REGION_NAME
    started = time.monotonic()
    status_code = None
    is_up = False
    error = ""
    detail: dict = {}
    response = None
    try:
        with httpx.Client(timeout=settings.CHECK_TIMEOUT_SECONDS, follow_redirects=False) as client:
            current = monitor.url
            for _ in range(settings.CHECK_MAX_REDIRECTS + 1):
                current = validate_target_url(current)
                response = client.get(current, headers={"User-Agent": "StatusMonitor/1.0", "Accept": "*/*"})
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
        if is_up and monitor.kind == "keyword":
            is_up, error, detail = _assert_keyword(monitor, response)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        # Timeouts + TLS/DNS failures (httpx/OSError) and SSRF rejections (ValueError).
        error = str(exc)[:400]
        is_up = False

    response_ms = int((time.monotonic() - started) * 1000)
    return record_check_result(
        monitor,
        is_up=is_up,
        status_code=status_code,
        response_ms=response_ms,
        error=error,
        region=region,
        detail=detail,
    )


def _assert_keyword(monitor: Monitor, response) -> tuple[bool, str, dict]:
    """Evaluate a keyword/content assertion against the fetched page."""
    config = monitor.config or {}
    phrase = str(config.get("keyword", "")).strip()
    match = str(config.get("match", "contains")).lower()
    if match not in ("contains", "not_contains"):
        match = "contains"
    case_sensitive = bool(config.get("case_sensitive", False))
    text = getattr(response, "text", "") or ""
    text = text[: settings.CHECK_MAX_BODY_BYTES]
    detail = {
        "keyword": phrase[:200],
        "match": match,
        "found": False,
        "body_bytes": len(text),
    }
    if not phrase:
        return False, "Keyword is not configured.", detail
    haystack = text if case_sensitive else text.casefold()
    needle = phrase if case_sensitive else phrase.casefold()
    found = needle in haystack
    detail["found"] = found
    if match == "contains" and not found:
        return False, f"Keyword not found: {phrase[:100]}", detail
    if match == "not_contains" and found:
        return False, f"Unexpected keyword present: {phrase[:100]}", detail
    return True, "", detail


def uptime_stats(monitor: Monitor, hours: int = 24) -> dict:
    """Percentages + per-hour buckets for the last ``hours``."""
    cutoff = timezone.now() - timedelta(hours=hours)
    checks = list(Check.objects.filter(monitor=monitor, checked_at__gte=cutoff).order_by("checked_at"))
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
            series.append({"bucket": cursor.isoformat(), "up_ratio": ratio, "samples": info["samples"]})
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
    return {row["monitor_id"]: (round(row["up"] / row["total"] * 100, 2) if row["total"] else None) for row in rows}


# --------------------------------------------------------------------------
# Domain expiry monitoring (RDAP — no API key, no extra dependency)
# --------------------------------------------------------------------------
def normalize_domain(value: str) -> str:
    """Validate/normalize a domain name (IDN → punycode)."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("A domain name is required.")
    if "://" in raw:
        host = urlparse(raw).hostname or ""
    else:
        host = raw.split("/", 1)[0].split(":", 1)[0]
    host = host.strip(".").lower()
    if not host or "." not in host:
        raise ValueError("Enter a full domain name, e.g. example.com.")
    if any(ch.isspace() for ch in host):
        raise ValueError("The domain name cannot contain spaces.")
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("That domain name is not valid.") from exc
    if len(ascii_host) > 253 or not re.fullmatch(r"[a-z0-9.-]+", ascii_host):
        raise ValueError("That domain name is not valid.")
    labels = ascii_host.split(".")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        raise ValueError("That domain name is not valid.")
    try:
        ipaddress.ip_address(ascii_host)
    except ValueError:
        pass
    else:
        raise ValueError("Enter a domain name, not an IP address.")
    return ascii_host


def domain_alert_level(days: int | None) -> str:
    if days is None:
        return ""
    if days <= settings.DOMAIN_CRITICAL_DAYS:
        return "critical"
    if days <= settings.DOMAIN_WARN_DAYS:
        return "warn"
    return ""


def _rdap_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _rdap_registrar(payload: dict) -> str:
    for entity in payload.get("entities") or []:
        if "registrar" not in (entity.get("roles") or []):
            continue
        vcard = entity.get("vcardArray")
        if isinstance(vcard, list) and len(vcard) > 1:
            for item in vcard[1]:
                if isinstance(item, list) and item and item[0] == "fn" and len(item) > 3:
                    return str(item[3])[:255]
        if entity.get("handle"):
            return str(entity["handle"])[:255]
    return ""


def check_domain(monitor: Monitor) -> dict:
    """Look up a domain's registration expiry via RDAP and persist it."""
    domain = normalize_domain((monitor.config or {}).get("domain") or monitor.url)
    expires_at = None
    days_remaining = None
    registrar = ""
    error = ""
    try:
        with httpx.Client(
            timeout=settings.CHECK_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": "StatusMonitor/1.0",
                "Accept": "application/rdap+json, application/json",
            },
        ) as client:
            response = client.get(f"https://rdap.org/domain/{domain}")
            response.raise_for_status()
            payload = response.json()
        for event in payload.get("events") or []:
            action = str(event.get("eventAction", "")).lower()
            if action in ("expiration", "expiry", "registration expiration"):
                expires_at = _rdap_datetime(event.get("eventDate"))
                if expires_at is not None:
                    break
        registrar = _rdap_registrar(payload)
        if expires_at is None:
            error = "RDAP response did not include an expiration date."
        else:
            days_remaining = (expires_at - datetime.now(UTC)).days
    except (httpx.HTTPError, ValueError, OSError, AttributeError) as exc:
        error = str(exc)[:400]

    previous = getattr(monitor, "domain", None)
    if expires_at is None and previous is not None:
        expires_at = previous.expires_at
        days_remaining = previous.days_remaining
    if days_remaining is None:
        status = "unknown"
    elif days_remaining < 0:
        status = "expired"
    elif days_remaining <= settings.DOMAIN_CRITICAL_DAYS:
        status = "critical"
    elif days_remaining <= settings.DOMAIN_WARN_DAYS:
        status = "expiring"
    else:
        status = "ok"
    record, _ = DomainRegistration.objects.update_or_create(
        monitor=monitor,
        defaults={
            "domain": domain,
            "expires_at": expires_at,
            "days_remaining": days_remaining,
            "registrar": registrar,
            "status": status,
            "error": error,
        },
    )
    return {
        "domain": domain,
        "expires_at": expires_at,
        "days_remaining": days_remaining,
        "registrar": registrar,
        "status": status,
        "error": error,
        "alert_level": record.alert_level,
    }


def record_domain_result(monitor: Monitor, result: dict, region: str | None = None) -> dict:
    """Record a domain sweep as a check; only an expired domain is 'down'."""
    days = result.get("days_remaining")
    is_up = days is None or days >= 0
    return record_check_result(
        monitor,
        is_up=is_up,
        status_code=None,
        response_ms=None,
        error=result.get("error", ""),
        region=region,
        detail={
            "domain": result.get("domain", ""),
            "days_remaining": days,
            "registrar": result.get("registrar", ""),
        },
    )


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
    checks = Check.objects.filter(monitor=monitor, checked_at__gte=cutoff).order_by("region", "-checked_at")
    per_region: dict[str, dict] = {}
    for check in checks:
        entry = per_region.setdefault(check.region, {"total": 0, "up": 0, "latest": check})
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
                "uptime_percent": (round(entry["up"] / entry["total"] * 100, 2) if entry["total"] else None),
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
    Check.objects.create(monitor=monitor, is_up=True, error="heartbeat", region=settings.REGION_NAME)
    if previous == Monitor.Status.DOWN:
        Incident.objects.filter(monitor=monitor, ended_at=None).update(ended_at=now)
        from notifications.services import enqueue_state_transition

        enqueue_state_transition(monitor, previous, Monitor.Status.UP, {"error": "heartbeat resumed"})
        logger.info("heartbeat resumed: monitor=%s", monitor.pk)
    return {"is_up": True, "status_code": None, "response_ms": None, "error": "heartbeat"}


def evaluate_heartbeat(monitor: Monitor) -> dict:
    """Mark a heartbeat monitor down when no ping arrived within interval+grace."""
    now = timezone.now()
    last = monitor.last_ping_at or monitor.created_at
    deadline = last + timedelta(seconds=monitor.check_interval_seconds + monitor.heartbeat_grace_seconds)
    if now <= deadline:
        return {"is_up": True, "status_code": None, "response_ms": None, "error": "heartbeat ok"}

    if monitor.last_status != Monitor.Status.DOWN:
        previous = monitor.last_status
        monitor.last_status = Monitor.Status.DOWN
        monitor.last_checked_at = now
        monitor.save(update_fields=["last_status", "last_checked_at", "updated_at"])
        Check.objects.create(monitor=monitor, is_up=False, error="heartbeat missed", region=settings.REGION_NAME)
        Incident.objects.create(monitor=monitor, started_at=now)
        suppressed = MaintenanceWindow.objects.filter(monitor=monitor, starts_at__lte=now, ends_at__gte=now).exists()
        if not suppressed:
            from notifications.services import enqueue_state_transition

            enqueue_state_transition(monitor, previous, Monitor.Status.DOWN, {"error": "heartbeat missed"})
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
