"""Cron entrypoint: refresh TLS certificate expiry for https monitors.

Schedule daily (e.g. ``0 6 * * *``). Fires an outbox alert only when a
certificate crosses into the warning window (SSL_WARN_DAYS) or the critical
window (SSL_CRITICAL_DAYS), so you aren't spammed every sweep.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from monitors.models import Monitor
from monitors.services import check_ssl
from notifications.services import enqueue_ssl_alert


def _level_for(days: int | None) -> str:
    if days is None:
        return ""
    if days <= settings.SSL_CRITICAL_DAYS:
        return "critical"
    if days <= settings.SSL_WARN_DAYS:
        return "warn"
    return ""


class Command(BaseCommand):
    help = "Check TLS certificate expiry for all https monitors (schedule daily)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-alert even if the alert level has not changed.",
        )

    def handle(self, *args, **options):
        monitors = [
            m
            for m in Monitor.objects.filter(is_active=True)
            if m.url.lower().startswith("https://")
        ]
        checked = alerted = 0
        for monitor in monitors:
            try:
                result = check_ssl(monitor)
            except ValueError as exc:  # SSRF / non-https guard
                self.stdout.write(self.style.WARNING(f"{monitor.name}: skipped ({exc})"))
                continue

            checked += 1
            record = monitor.ssl
            new_level = _level_for(result["days_remaining"])
            previous = record.alert_level or ""
            changed = new_level != previous
            escalated = _LEVEL_ORDER.get(new_level, 0) > _LEVEL_ORDER.get(previous, 0)

            if new_level and (changed or escalated or options["force"]):
                enqueue_ssl_alert(monitor, result["days_remaining"], new_level)
                alerted += 1
            if new_level != previous:
                record.alert_level = new_level
                record.save(update_fields=["alert_level"])

            summary = (
                f"{result['days_remaining']}d left"
                if result["days_remaining"] is not None
                else result["error"] or "no certificate"
            )
            self.stdout.write(f"{monitor.name}: {summary} (level={new_level or 'ok'})")

        self.stdout.write(
            self.style.SUCCESS(f"Checked {checked} certificate(s); {alerted} alert(s) queued.")
        )


_LEVEL_ORDER = {"": 0, "warn": 1, "critical": 2}
