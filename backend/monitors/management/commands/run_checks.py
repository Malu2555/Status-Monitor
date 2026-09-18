"""Cron entrypoint: check every monitor whose interval has elapsed.

Schedule this every minute via cron (Linux) or Task Scheduler (Windows) —
see scripts/run_checks_scheduled.ps1 and scripts/crontab.example.
"""

from django.core.management.base import BaseCommand

from monitors.models import Monitor
from monitors.services import run_check, should_check


class Command(BaseCommand):
    help = "Run all due monitor checks (schedule every minute)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Check every active monitor regardless of its interval.",
        )

    def handle(self, *args, **options):
        monitors = list(Monitor.objects.filter(is_active=True))
        if not options["force"]:
            monitors = [monitor for monitor in monitors if should_check(monitor)]

        for monitor in monitors:
            result = run_check(monitor)
            status = "up" if result["is_up"] else "down"
            detail = result["status_code"] or result["error"] or "unknown"
            self.stdout.write(f"{monitor.name}: {status} ({detail}, {result['response_ms']}ms)")

        self.stdout.write(self.style.SUCCESS(f"Checked {len(monitors)} monitor(s)."))
