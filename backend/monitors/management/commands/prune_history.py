"""Retention housekeeping for append-heavy tables.

`Check`, `AbuseEvent`, `AuditLogEntry` and delivered outbox rows grow forever on
a free Supabase plan. This command keeps the working set bounded; raw check rows
are the bulk of the data, so they have the shortest default window.

Scheduled daily at 03:30 UTC by `run_scheduler`; run manually with `--dry-run`
first when changing retention.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import AbuseEvent, AccountActionToken, BlockedIP, RevokedRefreshToken
from audit.models import AuditLogEntry
from monitors.models import Check
from notifications.models import NotificationDelivery

BATCH = 1000


class Command(BaseCommand):
    help = "Delete old checks, delivered notifications, audit/abuse rows and expired tokens."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Raw Check retention (days).")
        parser.add_argument("--audit-days", type=int, default=180, help="Audit retention (days).")
        parser.add_argument("--abuse-days", type=int, default=90, help="Abuse event retention (days).")
        parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting.")

    def handle(self, *args, **options):
        now = timezone.now()
        days = max(options["days"], 1)
        audit_days = max(options["audit_days"], days)
        abuse_days = max(options["abuse_days"], days)
        dry_run = options["dry_run"]

        jobs = [
            (
                Check.objects.filter(checked_at__lt=now - timedelta(days=days)),
                f"checks older than {days}d",
            ),
            (
                NotificationDelivery.objects.filter(
                    created_at__lt=now - timedelta(days=days),
                    status__in=[
                        NotificationDelivery.Status.SENT,
                        NotificationDelivery.Status.DEAD,
                    ],
                ),
                f"delivered/dead outbox rows older than {days}d",
            ),
            (
                AuditLogEntry.objects.filter(occurred_at__lt=now - timedelta(days=audit_days)),
                f"audit rows older than {audit_days}d",
            ),
            (
                AbuseEvent.objects.filter(created_at__lt=now - timedelta(days=abuse_days)),
                f"abuse events older than {abuse_days}d",
            ),
            (
                BlockedIP.objects.filter(expires_at__isnull=False, expires_at__lt=now),
                "expired IP blocks",
            ),
            (
                AccountActionToken.objects.filter(expires_at__lt=now - timedelta(days=1)),
                "expired account tokens",
            ),
            (
                RevokedRefreshToken.objects.filter(expires_at__lt=now),
                "expired refresh-token blacklist entries",
            ),
        ]

        for queryset, label in jobs:
            count = queryset.count()
            if dry_run:
                self.stdout.write(f"[dry-run] {label}: {count}")
                continue
            deleted = self._delete_in_batches(queryset)
            self.stdout.write(self.style.SUCCESS(f"{label}: deleted {deleted}"))

        if dry_run:
            self.stdout.write("[dry-run] nothing deleted")

    def _delete_in_batches(self, queryset) -> int:
        model = queryset.model
        total = 0
        while True:
            ids = list(queryset.values_list("pk", flat=True)[:BATCH])
            if not ids:
                return total
            deleted, _ = model.objects.filter(pk__in=ids).delete()
            total += deleted
