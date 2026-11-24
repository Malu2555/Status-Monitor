"""Cron entrypoint: refresh domain registration expiry (RDAP).

Schedule daily (e.g. ``30 6 * * *``). Mirrors ``check_ssl``: an alert is only
queued when the threshold level changes ("" → warn → critical).
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from monitors.models import DomainRegistration, Monitor
from monitors.services import (
    check_domain,
    domain_alert_level,
    record_domain_result,
    should_check,
)
from notifications.services import enqueue_domain_alert


class Command(BaseCommand):
    help = "Check domain registration expiry for kind='domain' monitors (schedule daily)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Check every domain monitor and re-alert even without a level change.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max monitors to check in this pass (0 = all due).",
        )

    def handle(self, *args, **options):
        monitors = list(Monitor.objects.filter(is_active=True, kind="domain"))
        if not options["force"]:
            monitors = [monitor for monitor in monitors if should_check(monitor)]
        if options["limit"] and options["limit"] > 0:
            monitors = monitors[: options["limit"]]

        checked = alerted = 0
        for monitor in monitors:
            try:
                result = check_domain(monitor)
            except ValueError as exc:
                self.stdout.write(self.style.WARNING(f"{monitor.name}: skipped ({exc})"))
                continue

            checked += 1
            previous_level = result.get("alert_level", "")
            new_level = domain_alert_level(result.get("days_remaining"))
            escalated = {"": 0, "warn": 1, "critical": 2}[new_level] > {
                "": 0,
                "warn": 1,
                "critical": 2,
            }[previous_level]
            days_remaining = result.get("days_remaining")
            if (
                new_level
                and days_remaining is not None
                and (new_level != previous_level or escalated or options["force"])
            ):
                enqueue_domain_alert(monitor, int(days_remaining), new_level)
                alerted += 1
            if new_level != previous_level:
                DomainRegistration.objects.filter(monitor=monitor).update(alert_level=new_level)

            record_domain_result(monitor, result)
            summary = (
                f"{result['days_remaining']}d left"
                if result.get("days_remaining") is not None
                else result.get("error") or "unknown"
            )
            self.stdout.write(f"{monitor.name}: {summary} (level={new_level or 'ok'})")

        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {checked} domain(s); {alerted} alert(s) queued "
                f"(warn={settings.DOMAIN_WARN_DAYS}d, critical={settings.DOMAIN_CRITICAL_DAYS}d)."
            )
        )
