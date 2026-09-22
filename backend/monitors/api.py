"""Monitor CRUD (auth) + free public status feed (throttled).

HTTP status codes: 200 OK · 201 created · 204 deleted · 400 plan limit ·
401 missing/invalid access token · 404 not found / not owned ·
422 URL rejected (scheme, SSRF) or interval below plan minimum · 429 rate limited.
"""
import logging

from django.utils import timezone
from ninja import Router, Status
from ninja.errors import HttpError

from accounts.auth import AuthBearer
from audit.services import audit_log
from config.throttling import MonitorAuthThrottle, PublicAnonThrottle

from .models import Incident, MaintenanceWindow, Monitor
from .schemas import (
    BucketOut,
    IncidentOut,
    MaintenanceOut,
    MonitorIn,
    MonitorOut,
    MonitorUpdateIn,
    PublicMonitorDetailOut,
    PublicMonitorOut,
    StatsOut,
)
from .services import bulk_uptime, uptime_stats, validate_target_url

logger = logging.getLogger("monitors")

router = Router(auth=AuthBearer())
public_router = Router(auth=None)


def _owned_or_404(request, monitor_id: int) -> Monitor:
    monitor = Monitor.objects.filter(pk=monitor_id, owner=request.auth).first()
    if monitor is None:
        raise HttpError(404, "Monitor not found.")
    return monitor


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


@router.post(
    "",
    response={201: MonitorOut},
    throttle=[MonitorAuthThrottle("100/h")],
    url_name="monitor_create",
)
def create_monitor(request, payload: MonitorIn):
    from billing.services import can_add_monitor, min_interval

    ok, reason = can_add_monitor(request.auth)
    if not ok:
        raise HttpError(400, reason)
    try:
        url = validate_target_url(payload.url)
    except ValueError as exc:
        logger.warning("monitor url rejected: user=%s url=%s (%s)", request.auth.username, payload.url, exc)
        raise HttpError(422, str(exc)) from exc
    minimum = min_interval(request.auth)
    if payload.check_interval_seconds < minimum:
        raise HttpError(422, f"Your plan requires a minimum check interval of {minimum}s.")
    monitor = Monitor.objects.create(
        owner=request.auth,
        name=payload.name.strip(),
        url=url,
        is_public=payload.is_public,
        check_interval_seconds=payload.check_interval_seconds,
    )
    logger.info("monitor created: id=%s user=%s", monitor.pk, request.auth.username)
    audit_log(
        request,
        "monitor.create",
        user=request.auth,
        monitor_id=monitor.pk,
        name=monitor.name,
        url=url,
    )
    return monitor


@router.get("/{monitor_id}", response=MonitorOut, throttle=[MonitorAuthThrottle("200/h")], url_name="monitor_get")
def get_monitor(request, monitor_id: int):
    return _owned_or_404(request, monitor_id)


@router.patch("/{monitor_id}", response=MonitorOut, throttle=[MonitorAuthThrottle("100/h")], url_name="monitor_update")
def update_monitor(request, monitor_id: int, payload: MonitorUpdateIn):
    monitor = _owned_or_404(request, monitor_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("url"):
        try:
            updates["url"] = validate_target_url(updates["url"])
        except ValueError as exc:
            raise HttpError(422, str(exc)) from exc
    if "check_interval_seconds" in updates:
        from billing.services import min_interval

        minimum = min_interval(request.auth)
        if updates["check_interval_seconds"] < minimum:
            raise HttpError(422, f"Your plan requires a minimum check interval of {minimum}s.")
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


@router.delete("/{monitor_id}", throttle=[MonitorAuthThrottle("100/h")], url_name="monitor_delete")
def delete_monitor(request, monitor_id: int):
    monitor = _owned_or_404(request, monitor_id)
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
            )
            for incident in recent_incidents
        ],
        series=[BucketOut(**bucket) for bucket in stats_24h["series"]],
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
