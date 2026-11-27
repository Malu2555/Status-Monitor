"""Monitor CRUD (auth) + free public status feed (throttled).

HTTP status codes: 200 OK · 201 created · 204 deleted · 400 plan limit ·
401 missing/invalid access token · 404 not found / not owned ·
422 URL rejected (scheme, SSRF) or interval below plan minimum · 429 rate limited.
"""

import csv
import html
import io
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError

from accounts.auth import ApiKeyAuth, AuthBearer
from audit.services import audit_log
from config.throttling import MonitorAuthThrottle, PublicAnonThrottle

from .models import (
    BrokenLink,
    CrawlRun,
    DomainRegistration,
    Incident,
    MaintenanceWindow,
    Monitor,
    StatusPage,
)
from .schemas import (
    BrokenLinkOut,
    BucketOut,
    CrawlReportOut,
    CrawlRunOut,
    DomainOut,
    HeartbeatOut,
    IncidentOut,
    MaintenanceIn,
    MaintenanceOut,
    MonitorIn,
    MonitorOut,
    MonitorUpdateIn,
    OverviewOut,
    PostmortemOut,
    PublicMonitorDetailOut,
    PublicMonitorOut,
    RegionOut,
    SslOut,
    StatsOut,
    StatusPageOut,
    UptimeBucketOut,
)
from .services import (
    bulk_uptime,
    draft_postmortem,
    normalize_domain,
    overview,
    record_heartbeat_ping,
    regional_statuses,
    uptime_buckets,
    uptime_stats,
    validate_target_url,
)

logger = logging.getLogger("monitors")

router = Router(auth=[AuthBearer(), ApiKeyAuth()])
public_router = Router(auth=None)


def _owned_or_404(request, monitor_id: int) -> Monitor:
    monitor = Monitor.objects.filter(pk=monitor_id, owner=request.auth).first()
    if monitor is None:
        raise HttpError(404, "Monitor not found.")
    return monitor


def _require_write(request) -> None:
    """Reject mutations made with a read-only API token."""
    if getattr(request, "api_token_scope", "write") == "read":
        raise HttpError(403, "This API token is read-only.")


SLOW_KINDS = ("domain", "broken_links")


def _clean_config(kind: str, config: dict | None, url: str) -> tuple[dict, str]:
    """Validate/normalize type-specific config; returns (config, display_url)."""
    cleaned = dict(config or {})
    if len(str(cleaned)) > 4000:
        raise HttpError(422, "Monitor settings are too large.")

    if kind in ("http", "keyword", "broken_links"):
        try:
            url = validate_target_url(url)
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc

    if kind == "keyword":
        phrase = str(cleaned.get("keyword", "")).strip()
        if not phrase or len(phrase) > 500:
            raise HttpError(422, "A keyword between 1 and 500 characters is required.")
        match = str(cleaned.get("match", "contains")).lower()
        if match not in ("contains", "not_contains"):
            raise HttpError(422, "Keyword match must be 'contains' or 'not_contains'.")
        return {
            "keyword": phrase,
            "match": match,
            "case_sensitive": bool(cleaned.get("case_sensitive", False)),
        }, url

    if kind == "domain":
        try:
            domain = normalize_domain(str(cleaned.get("domain") or url))
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc
        return {"domain": domain}, f"https://{domain}"

    if kind == "broken_links":
        try:
            max_pages = int(cleaned.get("max_pages", 25))
            max_depth = int(cleaned.get("max_depth", 2))
        except (TypeError, ValueError) as exc:
            raise HttpError(422, "Crawl limits must be numbers.") from exc
        return {
            "max_pages": min(max(max_pages, 1), 100),
            "max_depth": min(max(max_depth, 1), 3),
            "check_images": bool(cleaned.get("check_images", False)),
            "check_external": bool(cleaned.get("check_external", False)),
        }, url

    return {}, url


def _interval_for(kind: str, requested: int, minimum: int) -> int:
    """Apply per-kind interval floors (daily sweeps for domain/crawl)."""
    if kind in SLOW_KINDS and requested < 3600:
        requested = 86400
    if requested < minimum:
        raise HttpError(422, f"Your plan requires a minimum check interval of {minimum}s.")
    if kind in SLOW_KINDS and requested < 3600:
        raise HttpError(422, "This monitor type requires an interval of at least 1 hour.")
    return requested


# --------------------------------------------------------------------------
# Private CRUD
# --------------------------------------------------------------------------
@router.get("", response=list[MonitorOut], throttle=[MonitorAuthThrottle("200/h")], url_name="monitor_list")
def list_monitors(
    request,
    limit: int = 0,
    offset: int = 0,
    sort: str = "-created_at",
    status: str = "",
    is_active: str = "",
):
    """List monitors with optional server-side pagination/sort/filter.

    Defaults are backward compatible: everything, newest first.
    sort: name | -name | created_at | -created_at | last_checked_at | -last_checked_at
    """
    queryset = Monitor.objects.filter(owner=request.auth)
    if status in ("up", "down", "unknown"):
        queryset = queryset.filter(last_status=status)
    if is_active in ("true", "false"):
        queryset = queryset.filter(is_active=is_active == "true")
    if sort in ("name", "-name", "created_at", "-created_at", "last_checked_at", "-last_checked_at"):
        queryset = queryset.order_by(sort)
    if limit and limit > 0:
        return list(queryset[offset : offset + min(limit, 100)])
    return list(queryset)


@router.get("/overview", response=OverviewOut, throttle=[MonitorAuthThrottle("120/h")], url_name="monitor_overview")
def monitor_overview(request):
    """One-shot aggregate for the dashboard overview page (no per-monitor N+1)."""
    return overview(request.auth)


@router.post(
    "",
    response={201: MonitorOut},
    throttle=[MonitorAuthThrottle("100/h")],
    url_name="monitor_create",
)
def create_monitor(request, payload: MonitorIn):
    from billing.services import can_add_monitor, min_interval

    _require_write(request)
    ok, reason = can_add_monitor(request.auth)
    if not ok:
        raise HttpError(400, reason)
    interval = _interval_for(payload.kind, payload.check_interval_seconds, min_interval(request.auth))

    if payload.kind == "heartbeat":
        url = ""
        config = {}
        heartbeat_token = secrets.token_urlsafe(24)
    else:
        try:
            config, url = _clean_config(payload.kind, payload.config, payload.url)
        except HttpError as exc:
            logger.warning(
                "monitor config rejected: user=%s kind=%s (%s)",
                request.auth.username,
                payload.kind,
                str(exc),
            )
            raise
        heartbeat_token = None

    monitor = Monitor.objects.create(
        owner=request.auth,
        name=payload.name.strip(),
        url=url,
        is_public=payload.is_public,
        check_interval_seconds=interval,
        kind=payload.kind,
        config=config,
        heartbeat_token=heartbeat_token,
        heartbeat_grace_seconds=payload.heartbeat_grace_seconds,
    )
    logger.info(
        "monitor created: id=%s user=%s kind=%s",
        monitor.pk,
        request.auth.username,
        monitor.kind,
    )
    audit_log(
        request,
        "monitor.create",
        user=request.auth,
        monitor_id=monitor.pk,
        name=monitor.name,
        url=url,
        monitor_kind=monitor.kind,
    )
    return monitor


@router.get(
    "/export.csv",
    throttle=[MonitorAuthThrottle("20/h")],
    url_name="monitor_export",
)
def export_monitors(request, hours: int = 720):
    """Compliance report: per-monitor uptime + incident counts as CSV."""
    hours = min(max(hours, 1), 8760)
    cutoff = timezone.now() - timedelta(hours=hours)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "monitor",
            "kind",
            "url",
            "last_status",
            "uptime_percent",
            "checks_total",
            "checks_up",
            "incidents",
            "last_checked_at",
        ]
    )
    for monitor in Monitor.objects.filter(owner=request.auth).order_by("name"):
        stats = uptime_stats(monitor, hours=hours)
        incidents = Incident.objects.filter(monitor=monitor, started_at__gte=cutoff).count()
        writer.writerow(
            [
                monitor.name,
                monitor.kind,
                monitor.url,
                monitor.last_status,
                "" if stats["uptime_percent"] is None else stats["uptime_percent"],
                stats["total_checks"],
                stats["up_checks"],
                incidents,
                monitor.last_checked_at.isoformat() if monitor.last_checked_at else "",
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="status-report-{hours}h.csv"'
    return response


@router.get("/{monitor_id}", response=MonitorOut, throttle=[MonitorAuthThrottle("200/h")], url_name="monitor_get")
def get_monitor(request, monitor_id: int):
    return _owned_or_404(request, monitor_id)


@router.patch("/{monitor_id}", response=MonitorOut, throttle=[MonitorAuthThrottle("100/h")], url_name="monitor_update")
def update_monitor(request, monitor_id: int, payload: MonitorUpdateIn):
    monitor = _owned_or_404(request, monitor_id)
    _require_write(request)
    updates = payload.model_dump(exclude_unset=True)
    if "config" in updates or ("url" in updates and monitor.kind == "domain"):
        try:
            config, clean_url = _clean_config(
                monitor.kind,
                updates.get("config", monitor.config),
                updates.get("url", monitor.url),
            )
        except HttpError as exc:
            raise HttpError(422, str(exc)) from exc
        updates["config"] = config
        if monitor.kind == "domain":
            updates["url"] = clean_url
    if updates.get("url") and monitor.kind in ("http", "keyword", "broken_links"):
        try:
            updates["url"] = validate_target_url(updates["url"])
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc
    if "check_interval_seconds" in updates:
        from billing.services import min_interval

        value = updates["check_interval_seconds"]
        if monitor.kind in SLOW_KINDS and value < 3600:
            raise HttpError(422, "This monitor type requires an interval of at least 1 hour.")
        if value < min_interval(request.auth):
            raise HttpError(
                422,
                f"Your plan requires a minimum check interval of {min_interval(request.auth)}s.",
            )
    for field, value in updates.items():
        setattr(monitor, field, value)
    monitor.save()
    logger.info("monitor updated: id=%s user=%s", monitor.pk, request.auth.username)
    audit_log(
        request,
        "monitor.update",
        user=request.auth,
        monitor_id=monitor.pk,
        fields=sorted(updates.keys()),
    )
    return monitor


@router.delete(
    "/{monitor_id}", response={204: None}, throttle=[MonitorAuthThrottle("100/h")], url_name="monitor_delete"
)
def delete_monitor(request, monitor_id: int):
    monitor = _owned_or_404(request, monitor_id)
    _require_write(request)
    name = monitor.name
    monitor_id = monitor.pk
    monitor.delete()
    logger.info("monitor deleted: id=%s user=%s", monitor_id, request.auth.username)
    audit_log(
        request,
        "monitor.delete",
        user=request.auth,
        monitor_id=monitor_id,
        name=name,
    )
    return Status(204, None)


@router.get("/{monitor_id}/stats", response=StatsOut, throttle=[MonitorAuthThrottle("120/h")], url_name="monitor_stats")
def monitor_stats(request, monitor_id: int, hours: int = 24):
    monitor = _owned_or_404(request, monitor_id)
    return uptime_stats(monitor, hours=min(max(hours, 1), 720))


@router.get(
    "/{monitor_id}/uptime-buckets",
    response=list[UptimeBucketOut],
    throttle=[MonitorAuthThrottle("120/h")],
    url_name="monitor_uptime_buckets",
)
def monitor_uptime_buckets(request, monitor_id: int, hours: int = 24, bucket_hours: int = 1):
    """Contiguous per-bucket uptime + latency series for the detail-page graph."""
    monitor = _owned_or_404(request, monitor_id)
    return uptime_buckets(monitor, hours=hours, bucket_hours=bucket_hours)


# --------------------------------------------------------------------------
# Incident history
# --------------------------------------------------------------------------
@router.get(
    "/{monitor_id}/incidents",
    response=list[IncidentOut],
    throttle=[MonitorAuthThrottle("200/h")],
    url_name="monitor_incidents",
)
def monitor_incidents(request, monitor_id: int, limit: int = 20, offset: int = 0):
    """Paged incident history for the dashboard timeline (newest first)."""
    monitor = _owned_or_404(request, monitor_id)
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    incidents = Incident.objects.filter(monitor=monitor).order_by("-started_at")[offset : offset + limit]
    return [
        IncidentOut(
            id=incident.pk,
            started_at=incident.started_at,
            ended_at=incident.ended_at,
            checks_down=incident.checks_down,
            last_status_code=incident.last_status_code,
            postmortem=incident.postmortem,
        )
        for incident in incidents
    ]


# --------------------------------------------------------------------------
# Maintenance windows (planned downtime suppresses alerts)
# --------------------------------------------------------------------------
def _window_out(monitor, window) -> MaintenanceOut:
    return MaintenanceOut(
        id=window.pk,
        monitor_id=monitor.pk,
        monitor_name=monitor.name,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        note=window.note,
    )


@router.get(
    "/{monitor_id}/maintenance",
    response=list[MaintenanceOut],
    throttle=[MonitorAuthThrottle("200/h")],
    url_name="monitor_maintenance_list",
)
def monitor_maintenance_list(request, monitor_id: int):
    monitor = _owned_or_404(request, monitor_id)
    return [
        _window_out(monitor, window)
        for window in MaintenanceWindow.objects.filter(monitor=monitor).order_by("starts_at")
    ]


@router.post(
    "/{monitor_id}/maintenance",
    response={201: MaintenanceOut},
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="monitor_maintenance_create",
)
def monitor_maintenance_create(request, monitor_id: int, payload: MaintenanceIn):
    monitor = _owned_or_404(request, monitor_id)
    _require_write(request)
    if payload.ends_at <= payload.starts_at:
        raise HttpError(422, "The window must end after it starts.")
    if (payload.ends_at - payload.starts_at).total_seconds() > 30 * 86400:
        raise HttpError(422, "Maintenance windows are limited to 30 days.")
    conflict = (
        MaintenanceWindow.objects.filter(monitor=monitor, starts_at__lt=payload.ends_at, ends_at__gt=payload.starts_at)
        .order_by("starts_at")
        .first()
    )
    if conflict is not None:
        raise HttpError(422, f"That overlaps an existing window (id {conflict.pk}).")
    window = MaintenanceWindow.objects.create(
        monitor=monitor,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        note=(payload.note or "").strip()[:200],
    )
    logger.info(
        "maintenance window created: monitor=%s id=%s user=%s",
        monitor.pk,
        window.pk,
        request.auth.username,
    )
    audit_log(
        request,
        "monitor.maintenance_created",
        user=request.auth,
        monitor_id=monitor.pk,
        window_id=window.pk,
    )
    return 201, _window_out(monitor, window)


@router.delete(
    "/{monitor_id}/maintenance/{window_id}",
    response={204: None},
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="monitor_maintenance_delete",
)
def monitor_maintenance_delete(request, monitor_id: int, window_id: int):
    monitor = _owned_or_404(request, monitor_id)
    _require_write(request)
    window = MaintenanceWindow.objects.filter(monitor=monitor, pk=window_id).first()
    if window is None:
        raise HttpError(404, "Maintenance window not found.")
    if window.starts_at <= timezone.now():
        raise HttpError(400, "That window has already started — cancel it in the admin.")
    window.delete()
    logger.info(
        "maintenance window deleted: monitor=%s id=%s user=%s",
        monitor.pk,
        window_id,
        request.auth.username,
    )
    audit_log(
        request,
        "monitor.maintenance_deleted",
        user=request.auth,
        monitor_id=monitor.pk,
        window_id=window_id,
    )
    return 204, None


@router.get(
    "/{monitor_id}/regions",
    response=list[RegionOut],
    throttle=[MonitorAuthThrottle("120/h")],
    url_name="monitor_regions",
)
def monitor_regions(request, monitor_id: int, hours: int = 24):
    """Per-region last status + uptime (the multi-region consensus view)."""
    monitor = _owned_or_404(request, monitor_id)
    return regional_statuses(monitor, hours=min(max(hours, 1), 720))


@router.get(
    "/{monitor_id}/ssl",
    response=SslOut,
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="monitor_ssl",
)
def monitor_ssl(request, monitor_id: int):
    """Latest TLS certificate state (populated by ``manage.py check_ssl``)."""
    monitor = _owned_or_404(request, monitor_id)
    record = getattr(monitor, "ssl", None)
    if record is None:
        return SslOut(
            subject="",
            issuer="",
            error="Not checked yet — run manage.py check_ssl.",
            alert_level="",
        )
    return SslOut(
        subject=record.subject,
        issuer=record.issuer,
        not_before=record.not_before,
        not_after=record.not_after,
        days_remaining=record.days_remaining,
        error=record.error,
        alert_level=record.alert_level,
        checked_at=record.checked_at,
    )


def _crawl_report(monitor: Monitor) -> CrawlReportOut:
    run = CrawlRun.objects.filter(monitor=monitor).first()
    links = BrokenLink.objects.filter(monitor=monitor, resolved_at__isnull=True)[:200]
    return CrawlReportOut(
        run=(
            CrawlRunOut(
                id=run.pk,
                started_at=run.started_at,
                finished_at=run.finished_at,
                pages_crawled=run.pages_crawled,
                links_checked=run.links_checked,
                broken_count=run.broken_count,
                error=run.error,
            )
            if run
            else None
        ),
        broken_links=[
            BrokenLinkOut(
                id=link.pk,
                source_url=link.source_url,
                target_url=link.target_url,
                status_code=link.status_code,
                error=link.error,
                first_seen_at=link.first_seen_at,
                last_seen_at=link.last_seen_at,
            )
            for link in links
        ],
    )


@router.get(
    "/{monitor_id}/domain",
    response=DomainOut,
    throttle=[MonitorAuthThrottle("60/h")],
    url_name="monitor_domain",
)
def monitor_domain(request, monitor_id: int):
    """Latest RDAP registration state for a domain-expiry monitor."""
    monitor = _owned_or_404(request, monitor_id)
    if monitor.kind != "domain":
        raise HttpError(400, "This monitor is not a domain-expiry monitor.")
    domain = (monitor.config or {}).get("domain") or monitor.url
    record = DomainRegistration.objects.filter(monitor=monitor).first()
    if record is None:
        return DomainOut(
            domain=normalize_domain(domain),
            status="unknown",
            error="Not checked yet — run manage.py check_domains.",
        )
    return DomainOut(
        domain=record.domain,
        expires_at=record.expires_at,
        days_remaining=record.days_remaining,
        registrar=record.registrar,
        status=record.status,
        error=record.error,
        alert_level=record.alert_level,
        checked_at=record.checked_at,
    )


@router.get(
    "/{monitor_id}/crawl",
    response=CrawlReportOut,
    throttle=[MonitorAuthThrottle("120/h")],
    url_name="monitor_crawl",
)
def monitor_crawl(request, monitor_id: int):
    """Latest broken-link crawl summary + still-open dead links."""
    monitor = _owned_or_404(request, monitor_id)
    if monitor.kind != "broken_links":
        raise HttpError(400, "This monitor is not a broken-link monitor.")
    return _crawl_report(monitor)


@router.post(
    "/{monitor_id}/crawl/run",
    response=CrawlReportOut,
    throttle=[MonitorAuthThrottle("10/h")],
    url_name="monitor_crawl_run",
)
def monitor_crawl_run(request, monitor_id: int):
    """Run a broken-link crawl immediately (rate-limited)."""
    monitor = _owned_or_404(request, monitor_id)
    _require_write(request)
    if monitor.kind != "broken_links":
        raise HttpError(400, "This monitor is not a broken-link monitor.")
    from .crawling import crawl_monitor

    crawl_monitor(monitor, max_seconds=min(settings.CRAWL_MAX_SECONDS, 30))
    audit_log(
        request,
        "monitor.crawl_run",
        user=request.auth,
        monitor_id=monitor.pk,
    )
    return _crawl_report(monitor)


@router.post(
    "/{monitor_id}/incidents/{incident_id}/postmortem",
    response=PostmortemOut,
    throttle=[MonitorAuthThrottle("30/h")],
    url_name="incident_postmortem",
)
def incident_postmortem(request, monitor_id: int, incident_id: int):
    """Generate (or regenerate) a customer-facing postmortem draft."""
    monitor = _owned_or_404(request, monitor_id)
    _require_write(request)
    incident = Incident.objects.filter(pk=incident_id, monitor=monitor).first()
    if incident is None:
        raise HttpError(404, "Incident not found.")
    incident.postmortem = draft_postmortem(incident)
    incident.save(update_fields=["postmortem"])
    logger.info("postmortem drafted: monitor=%s incident=%s", monitor.pk, incident.pk)
    audit_log(
        request,
        "incident.postmortem_drafted",
        user=request.auth,
        monitor_id=monitor.pk,
        incident_id=incident.pk,
    )
    return PostmortemOut(postmortem=incident.postmortem)


# --------------------------------------------------------------------------
# Public feed (no auth; anyone can read)
# --------------------------------------------------------------------------
@public_router.get(
    "/monitors",
    response=list[PublicMonitorOut],
    throttle=[PublicAnonThrottle("60/m")],
    url_name="public_monitors",
)
def public_monitors(request):
    monitors = list(Monitor.objects.filter(is_active=True, is_public=True))
    uptime = bulk_uptime([monitor.pk for monitor in monitors])
    return [
        PublicMonitorOut(
            id=monitor.pk,
            name=monitor.name,
            url=monitor.url,
            kind=monitor.kind,
            last_status=monitor.last_status,
            last_status_code=monitor.last_status_code,
            last_response_ms=monitor.last_response_ms,
            last_checked_at=monitor.last_checked_at,
            uptime_24h=uptime.get(monitor.pk),
        )
        for monitor in monitors
    ]


@public_router.get(
    "/monitors/{monitor_id}",
    response=PublicMonitorDetailOut,
    throttle=[PublicAnonThrottle("60/m")],
    url_name="public_monitor_detail",
)
def public_monitor_detail(request, monitor_id: int):
    monitor = Monitor.objects.filter(pk=monitor_id, is_active=True, is_public=True).first()
    if monitor is None:
        raise HttpError(404, "Monitor not found.")
    stats_24h = uptime_stats(monitor, hours=24)
    stats_7d = uptime_stats(monitor, hours=168)
    stats_30d = uptime_stats(monitor, hours=720)
    recent_incidents = list(Incident.objects.filter(monitor=monitor).order_by("-started_at")[:10])
    return PublicMonitorDetailOut(
        id=monitor.pk,
        name=monitor.name,
        url=monitor.url,
        kind=monitor.kind,
        last_status=monitor.last_status,
        last_status_code=monitor.last_status_code,
        last_response_ms=monitor.last_response_ms,
        last_checked_at=monitor.last_checked_at,
        uptime_24h=stats_24h["uptime_percent"],
        uptime_7d=stats_7d["uptime_percent"],
        uptime_30d=stats_30d["uptime_percent"],
        incidents=[
            IncidentOut(
                id=incident.pk,
                started_at=incident.started_at,
                ended_at=incident.ended_at,
                checks_down=incident.checks_down,
                last_status_code=incident.last_status_code,
                postmortem=incident.postmortem,
            )
            for incident in recent_incidents
        ],
        series=[BucketOut(**bucket) for bucket in stats_24h["series"]],
        regions=[RegionOut(**region) for region in regional_statuses(monitor)],
    )


@public_router.get(
    "/maintenance",
    response=list[MaintenanceOut],
    throttle=[PublicAnonThrottle("60/m")],
    url_name="public_maintenance",
)
def public_maintenance(request):
    """Active maintenance windows on public monitors (for the status page)."""
    now = timezone.now()
    windows = (
        MaintenanceWindow.objects.filter(
            starts_at__lte=now,
            ends_at__gte=now,
            monitor__is_active=True,
            monitor__is_public=True,
        )
        .select_related("monitor")
        .order_by("ends_at")
    )
    return [
        MaintenanceOut(
            id=window.pk,
            monitor_id=window.monitor.pk,
            monitor_name=window.monitor.name,
            starts_at=window.starts_at,
            ends_at=window.ends_at,
            note=window.note,
        )
        for window in windows
    ]


@public_router.get(
    "/statuspages/{slug}",
    response=StatusPageOut,
    throttle=[PublicAnonThrottle("60/m")],
    url_name="public_statuspage",
)
def public_statuspage(request, slug: str):
    """A branded, per-customer public status page (subset of monitors)."""
    page = StatusPage.objects.filter(slug=slug, is_public=True, is_active=True).first()
    if page is None:
        raise HttpError(404, "Status page not found.")
    monitors = list(page.monitors.filter(is_active=True))
    uptime = bulk_uptime([monitor.pk for monitor in monitors])
    return StatusPageOut(
        slug=page.slug,
        title=page.title,
        description=page.description,
        theme_color=page.theme_color,
        monitors=[
            PublicMonitorOut(
                id=monitor.pk,
                name=monitor.name,
                url=monitor.url,
                kind=monitor.kind,
                last_status=monitor.last_status,
                last_status_code=monitor.last_status_code,
                last_response_ms=monitor.last_response_ms,
                last_checked_at=monitor.last_checked_at,
                uptime_24h=uptime.get(monitor.pk),
            )
            for monitor in monitors
        ],
    )


@public_router.get(
    "/badge/{monitor_id}.svg",
    auth=None,
    throttle=[PublicAnonThrottle("120/m")],
    url_name="public_badge",
)
def public_badge(request, monitor_id: int):
    """Embeddable SVG status badge: ``<img src="…/api/public/badge/5.svg">``."""
    monitor = Monitor.objects.filter(pk=monitor_id, is_active=True, is_public=True).first()
    if monitor is None:
        return HttpResponse("", status=404)
    colors = {"up": "#16a34a", "down": "#dc2626"}
    labels = {"up": "operational", "down": "down"}
    color = colors.get(monitor.last_status, "#6b7280")
    label = labels.get(monitor.last_status, "unknown")
    name = html.escape(monitor.name[:26])
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="220" height="20" role="img" '
        f'aria-label="{name}: {label}">'
        '<rect width="220" height="20" rx="3" fill="#111827"/>'
        f'<rect x="150" width="70" height="20" rx="3" fill="{color}"/>'
        f'<text x="8" y="14" fill="#f3f4f6" font-family="Verdana,sans-serif" font-size="11">{name}</text>'
        f'<text x="185" y="14" fill="#ffffff" font-family="Verdana,sans-serif" '
        f'font-size="11" text-anchor="middle">{label}</text>'
        "</svg>"
    )
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "max-age=60"
    return response


@public_router.post(
    "/heartbeat/{token}",
    auth=None,
    response=HeartbeatOut,
    throttle=[PublicAnonThrottle("120/m")],
    url_name="public_heartbeat",
)
def public_heartbeat(request, token: str):
    """Inbound ping for heartbeat (cron-job) monitors."""
    monitor = Monitor.objects.filter(heartbeat_token=token, is_active=True, kind="heartbeat").first()
    if monitor is None:
        raise HttpError(404, "Unknown heartbeat.")
    record_heartbeat_ping(monitor)
    return HeartbeatOut(detail="ok")
