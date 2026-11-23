"""Long-running scheduler for the production container.

Runs the minute jobs every ``--interval`` seconds and the daily sweeps once per
UTC day. ``--once`` performs a single pass (useful for smoke tests and tests);
``--all`` forces the daily jobs too.

Example (Containerfile CMD):
    python manage.py run_scheduler
"""

import logging
import time
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger("monitors")

DAILY_JOBS = {
    "prune_history": (3, 30),
    "check_ssl": (6, 0),
    "check_domains": (6, 30),
    "crawl_links": (7, 0),
}
MINUTE_JOBS = {"run_checks", "deliver_notifications"}
DEFAULT_MINUTE_JOBS = "run_checks,deliver_notifications"


class Command(BaseCommand):
    help = "Run the periodic checks and notification delivery loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Seconds between passes.")
        parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
        parser.add_argument("--all", action="store_true", help="Run daily jobs even if not due.")
        parser.add_argument("--jobs", default=DEFAULT_MINUTE_JOBS, help="Comma-separated minute jobs.")
        parser.add_argument(
            "--daily-jobs",
            default=",".join(DAILY_JOBS),
            help="Comma-separated daily jobs from: " + ", ".join(DAILY_JOBS),
        )

    def handle(self, *args, **options):
        minute_jobs = [job.strip() for job in options["jobs"].split(",") if job.strip()]
        daily_jobs = [job.strip() for job in options["daily_jobs"].split(",") if job.strip()]
        interval = max(options["interval"], 5)

        unknown = [job for job in minute_jobs if job not in MINUTE_JOBS]
        unknown += [job for job in daily_jobs if job not in DAILY_JOBS]
        if unknown:
            raise CommandError(f"Unknown scheduler job(s): {', '.join(sorted(set(unknown)))}")

        self.stdout.write(
            self.style.SUCCESS(f"Scheduler started (interval={interval}s, minute={minute_jobs}, daily={daily_jobs})")
        )
        try:
            while True:
                self._run(minute_jobs, "minute")
                self._run_daily(daily_jobs, force=options["all"])
                if options["once"]:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("\nScheduler stopped.")

    def _run(self, jobs: list[str], reason: str) -> None:
        for job in jobs:
            self._invoke(job, reason)

    def _run_daily(self, jobs: list[str], *, force: bool) -> None:
        now = timezone.now()
        for job in jobs:
            slot = DAILY_JOBS.get(job)
            if slot is None:
                self.stderr.write(f"Unknown daily job: {job}")
                continue
            due = force or (now.hour, now.minute) >= slot
            if not due:
                continue
            key = f"scheduler:daily:{job}:{now:%Y-%m-%d}"
            if cache.get(key):
                continue
            self._invoke(job, "daily")
            cache.set(key, True, 60 * 60 * 26)

    def _invoke(self, job: str, reason: str) -> None:
        buffer = StringIO()
        started = time.monotonic()
        try:
            call_command(job, stdout=buffer, stderr=buffer)
        except Exception as exc:  # one failing job must not stop the loop
            logger.exception("scheduler job failed: %s", job)
            self.stderr.write(f"[scheduler] {job} failed: {exc}")
            return
        elapsed = round((time.monotonic() - started) * 1000)
        output = buffer.getvalue().strip()
        logger.info("scheduler %s job %s (%sms): %s", reason, job, elapsed, output[:300])
        self.stdout.write(f"[scheduler] {job} ({reason}, {elapsed}ms): {output}")
