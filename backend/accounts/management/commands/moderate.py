"""Routine moderation without opening the Django admin.

Examples:
    python manage.py moderate disable_user alice@example.com --reason tos_violation
    python manage.py moderate enable_user alice@example.com
    python manage.py moderate block_ip 203.0.113.9 --hours 24 --reason scanning
    python manage.py moderate unblock_ip 203.0.113.9
    python manage.py moderate list_recent --days 7
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts import abuse
from accounts import services as account_services
from accounts.models import AbuseEvent, BlockedIP, User
from audit.services import audit_log

REASONS = ("manual", "tos_violation", "abuse", "chargeback", "self_deleted")


class Command(BaseCommand):
    help = "Moderate accounts and IP blocks without using the Django admin."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=("disable_user", "enable_user", "block_ip", "unblock_ip", "list_recent"),
        )
        parser.add_argument("target", nargs="?", help="username/email or IP address")
        parser.add_argument("--reason", default="manual", help="Disable/block reason")
        parser.add_argument("--hours", type=int, default=24, help="Block duration (0 = permanent)")
        parser.add_argument("--days", type=int, default=7, help="Window for list_recent")

    def handle(self, *args, **options):
        action = options["action"]
        target = (options.get("target") or "").strip()
        if action != "list_recent" and not target:
            raise CommandError("This action requires a target (username/email or IP).")

        if action in ("disable_user", "enable_user"):
            user = User.objects.filter(Q(username=target) | Q(email__iexact=target)).first()
            if user is None:
                raise CommandError(f"No user matches {target!r}.")
            if action == "disable_user":
                reason = options["reason"]
                if reason not in REASONS:
                    raise CommandError(f"Reason must be one of: {', '.join(REASONS)}")
                paused = account_services.disable_user(user, reason)
                audit_log(
                    None,
                    "moderation.user_disabled",
                    user=user,
                    reason=reason,
                    by="manage.py",
                    monitors_paused=paused,
                    channel="manage.py",
                )
                self.stdout.write(self.style.SUCCESS(f"Disabled {user.username}; paused {paused} monitor(s)."))
            else:
                resumed = account_services.enable_user(user)
                audit_log(
                    None,
                    "moderation.user_enabled",
                    user=user,
                    by="manage.py",
                    monitors_resumed=resumed,
                    channel="manage.py",
                )
                self.stdout.write(self.style.SUCCESS(f"Re-enabled {user.username}; resumed {resumed} monitor(s)."))
            return

        if action == "block_ip":
            hours = max(options["hours"], 0)
            seconds = hours * 3600 if hours else None
            abuse.block_ip(target, reason=options["reason"], auto=False, seconds=seconds)
            audit_log(
                None,
                "moderation.ip_blocked",
                reason=options["reason"],
                ip=target,
                by="manage.py",
                channel="manage.py",
            )
            self.stdout.write(self.style.SUCCESS(f"Blocked {target}."))
            return

        if action == "unblock_ip":
            removed = abuse.unblock_ip(target)
            audit_log(
                None,
                "moderation.ip_unblocked",
                ip=target,
                by="manage.py",
                channel="manage.py",
            )
            self.stdout.write(self.style.SUCCESS(f"Unblocked {target}." if removed else f"{target} was not blocked."))
            return

        # list_recent
        cutoff = timezone.now() - timedelta(days=max(options["days"], 1))
        self.stdout.write("Blocked IPs:")
        now = timezone.now()
        blocks = BlockedIP.objects.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).order_by("-created_at")[
            :20
        ]
        if not blocks:
            self.stdout.write("  (none)")
        for row in blocks:
            until = row.expires_at.isoformat() if row.expires_at else "permanent"
            self.stdout.write(f"  {row.ip}  auto={row.auto}  until={until}  {row.reason}")
        self.stdout.write("\nRecent abuse events:")
        for event in AbuseEvent.objects.filter(created_at__gte=cutoff)[:20]:
            self.stdout.write(f"  {event.created_at:%Y-%m-%d %H:%M}  {event.kind:<12} {event.ip}")
        self.stdout.write("\nPrivileged accounts:")
        for user in User.objects.filter(Q(is_staff=True) | Q(is_superuser=True))[:20]:
            self.stdout.write(f"  {user.username}  staff={user.is_staff}  superuser={user.is_superuser}")
