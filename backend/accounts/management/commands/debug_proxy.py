"""Diagnose client-IP attribution behind Render/Vercel proxies.

    python manage.py debug_proxy --latest
    python manage.py debug_proxy --remote 10.0.0.1 --xff "6.6.6.6, 1.2.3.4"

`--latest` reads recent audit payloads (login/register record the raw chain).
Increase PROXY_HOPS if the resolved IP is the Vercel edge rather than the browser.
"""

from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.abuse import client_ip
from audit.models import AuditLogEntry


class Command(BaseCommand):
    help = "Show trusted-proxy settings and resolve a sample client IP / recent audit rows."

    def add_arguments(self, parser):
        parser.add_argument("--latest", action="store_true", help="Show recent audit IP data.")
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--remote", default="", help="Sample REMOTE_ADDR")
        parser.add_argument("--xff", default="", help="Sample X-Forwarded-For chain")

    def handle(self, *args, **options):
        self.stdout.write(f"TRUSTED_PROXY_IPS={settings.TRUSTED_PROXY_IPS}")
        self.stdout.write(f"PROXY_HOPS={settings.PROXY_HOPS}")

        if options["remote"] or options["xff"]:
            request = SimpleNamespace(
                META={
                    "REMOTE_ADDR": options["remote"],
                    "HTTP_X_FORWARDED_FOR": options["xff"],
                }
            )
            self.stdout.write(
                f"sample remote={options['remote']!r} xff={options['xff']!r} -> client_ip={client_ip(request)!r}"
            )

        if options["latest"]:
            rows = AuditLogEntry.objects.filter(
                kind__in=[
                    "auth.login",
                    "auth.login_failed",
                    "auth.register",
                    "admin.login_success",
                ]
            ).order_by("-occurred_at")[: max(options["limit"], 1)]
            if not rows:
                self.stdout.write("No audit rows yet — perform a login first.")
            for row in rows:
                xff = (row.payload or {}).get("xff", "")
                remote = (row.payload or {}).get("remote", "")
                self.stdout.write(
                    f"{row.occurred_at:%Y-%m-%d %H:%M:%S} {row.kind:<20} ip={row.ip} remote={remote} xff={xff}"
                )
