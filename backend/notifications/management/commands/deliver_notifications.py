"""Cron entrypoint: send pending notification deliveries (every minute)."""

from django.core.management.base import BaseCommand

from notifications.services import deliver_pending


class Command(BaseCommand):
    help = "Send pending notification deliveries; schedule every minute."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=50, help="Max deliveries per run")
        parser.add_argument(
            "--max-attempts", type=int, default=8, help="Attempts before dead-lettering"
        )

    def handle(self, *args, **options):
        sent, failed, dead = deliver_pending(
            batch=options["batch"], max_attempts=options["max_attempts"]
        )
        self.stdout.write(f"sent={sent} failed={failed} dead={dead}")
