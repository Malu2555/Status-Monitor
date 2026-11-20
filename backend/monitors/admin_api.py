"""Operator-only HTTP triggers for the periodic management commands.

This lets a free external scheduler (GitHub Actions, cron-job.org, UptimeRobot)
drive the minute jobs when the host has no cron add-on — plus a manual button
for when the scheduler itself flakes.

Every endpoint requires a staff JWT and is throttled, so a leaked token cannot
burn the database. Intended for small deployments: one request holds a worker
for the duration of the sweep.
"""

from io import StringIO

from django.core.management import call_command
from ninja import Router, Schema
from ninja.errors import HttpError

from accounts.auth import AuthBearer
from audit.services import audit_log
from config.throttling import AdminJobThrottle, SessionAuthThrottle

router = Router(auth=AuthBearer())

JOB_THROTTLE = [AdminJobThrottle("120/h")]

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
]


class JobOut(Schema):
    name: str
    method: str
    schedule: str
    description: str


class RunOut(Schema):
    job: str
    output: str


def _require_staff(request) -> None:
    if not getattr(request.auth, "is_staff", False):
        raise HttpError(403, "Staff access required.")


def _run(request, command: str, job: str, **options) -> dict:
    _require_staff(request)
    buffer = StringIO()
    call_command(command, stdout=buffer, stderr=buffer, **options)
    output = buffer.getvalue().strip()
    audit_log(request, "admin.run_job", user=request.auth, job=job, options=options or {})
    return {"job": job, "output": output}


@router.get("", response=list[JobOut], throttle=[SessionAuthThrottle("60/m")], url_name="admin_run_index")
def index(request):
    """List the triggerable jobs so the SPA can render manual buttons."""
    _require_staff(request)
    return JOBS


@router.post("/run-checks", response=RunOut, throttle=JOB_THROTTLE, url_name="admin_run_checks")
def run_checks(request):
    return _run(request, "run_checks", "run-checks")


@router.post(
    "/deliver-notifications",
    response=RunOut,
    throttle=JOB_THROTTLE,
    url_name="admin_deliver_notifications",
)
def deliver_notifications(request):
    return _run(request, "deliver_notifications", "deliver-notifications")


@router.post("/check-ssl", response=RunOut, throttle=JOB_THROTTLE, url_name="admin_check_ssl")
def check_ssl_job(request, force: bool = False):
    return _run(request, "check_ssl", "check-ssl", force=force)
