"""Operator-only HTTP triggers for the periodic management commands.

Two authentication paths:
  * staff UI:    Authorization: Bearer <access JWT>  → requires is_superuser
  * scheduler:   X-Scheduler-Token: <SCHEDULER_TOKEN> → /api/admin/scheduler/{job}

The container scheduler normally calls the management commands directly; the
scheduler endpoint exists so an external driver (Cloudflare Worker, CI) can
trigger the same work without a human account.
"""

import hmac
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from ninja import Router, Schema
from ninja.errors import HttpError

from accounts.auth import AuthBearer
from audit.services import audit_log
from config.throttling import AdminJobThrottle, SchedulerThrottle, SessionAuthThrottle

router = Router(auth=AuthBearer())
scheduler_router = Router(auth=None)

JOB_THROTTLE = [AdminJobThrottle("120/h")]

JOB_COMMANDS = {
    "run-checks": "run_checks",
    "deliver-notifications": "deliver_notifications",
    "check-ssl": "check_ssl",
    "check-domains": "check_domains",
    "crawl-links": "crawl_links",
}

JOBS = [
    {
        "name": "run-checks",
        "method": "POST",
        "schedule": "every minute",
        "description": "Probe every monitor whose interval has elapsed.",
    },
    {
        "name": "deliver-notifications",
        "method": "POST",
        "schedule": "every minute",
        "description": "Drain the notification outbox (retries included).",
    },
    {
        "name": "check-ssl",
        "method": "POST",
        "schedule": "daily (06:00)",
        "description": "Refresh TLS expiry and queue escalated certificate alerts.",
    },
    {
        "name": "check-domains",
        "method": "POST",
        "schedule": "daily (06:30)",
        "description": "Refresh domain registration expiry (RDAP) and queue alerts.",
    },
    {
        "name": "crawl-links",
        "method": "POST",
        "schedule": "daily (07:00)",
        "description": "Crawl due broken-link monitors and queue new-link alerts.",
    },
]


class JobOut(Schema):
    name: str
    method: str
    schedule: str
    description: str


class RunOut(Schema):
    job: str
    output: str


def _require_superuser(request) -> None:
    """Admin job triggers are limited to superusers (not staff/moderation users)."""
    if not getattr(request.auth, "is_superuser", False):
        raise HttpError(403, "Superuser access required.")


def _require_scheduler(request) -> None:
    expected = getattr(settings, "SCHEDULER_TOKEN", "")
    provided = request.headers.get("X-Scheduler-Token", "")
    if not expected or not hmac.compare_digest(provided, expected):
        raise HttpError(403, "Invalid scheduler token.")


def _run(request, command: str, job: str, **options) -> dict:
    buffer = StringIO()
    call_command(command, stdout=buffer, stderr=buffer, **options)
    output = buffer.getvalue().strip()
    audit_log(
        request,
        "admin.run_job",
        user=getattr(request, "auth", None),
        job=job,
        options=options or {},
        channel="scheduler" if getattr(request, "auth", None) is None else "admin-api",
    )
    return {"job": job, "output": output}


@router.get("", response=list[JobOut], throttle=[SessionAuthThrottle("60/m")], url_name="admin_run_index")
def index(request):
    """List the triggerable jobs so the SPA can render manual buttons."""
    _require_superuser(request)
    return JOBS


@router.post("/run-checks", response=RunOut, throttle=JOB_THROTTLE, url_name="admin_run_checks")
def run_checks(request):
    _require_superuser(request)
    return _run(request, "run_checks", "run-checks")


@router.post(
    "/deliver-notifications",
    response=RunOut,
    throttle=JOB_THROTTLE,
    url_name="admin_deliver_notifications",
)
def deliver_notifications(request):
    _require_superuser(request)
    return _run(request, "deliver_notifications", "deliver-notifications")


@router.post("/check-ssl", response=RunOut, throttle=JOB_THROTTLE, url_name="admin_check_ssl")
def check_ssl_job(request, force: bool = False):
    _require_superuser(request)
    return _run(request, "check_ssl", "check-ssl", force=force)


@router.post("/check-domains", response=RunOut, throttle=JOB_THROTTLE, url_name="admin_check_domains")
def check_domains_job(request, force: bool = False):
    _require_superuser(request)
    return _run(request, "check_domains", "check-domains", force=force)


@router.post("/crawl-links", response=RunOut, throttle=JOB_THROTTLE, url_name="admin_crawl_links")
def crawl_links_job(request, limit: int = 0, max_seconds: int = 0):
    _require_superuser(request)
    return _run(
        request,
        "crawl_links",
        "crawl-links",
        limit=max(limit, 0),
        max_seconds=max(max_seconds, 0),
    )


@scheduler_router.post(
    "/{job}",
    response=RunOut,
    throttle=SchedulerThrottle("3000/h"),
    url_name="admin_scheduler_run_job",
)
def scheduler_run_job(request, job: str):
    """Machine-to-machine trigger authenticated with X-Scheduler-Token."""
    _require_scheduler(request)
    command = JOB_COMMANDS.get(job)
    if command is None:
        raise HttpError(404, "Unknown job.")
    return _run(request, command, job)
