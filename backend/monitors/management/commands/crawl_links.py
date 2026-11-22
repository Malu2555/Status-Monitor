"""Cron entrypoint: crawl kind='broken_links' monitors for dead links.

Schedule daily (e.g. ``0 7 * * *``) or every few hours. Each run respects the
monitor's own interval, a page budget, and a wall-clock budget.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from monitors.crawling import crawl_monitor
from monitors.models import Monitor
from monitors.services import should_check


class Command(BaseCommand):
    help = "Crawl due broken-link monitors (schedule daily)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Crawl every active broken-link monitor regardless of its interval.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max monitors to crawl in this pass (0 = all due).",
        )
        parser.add_argument(
            "--max-seconds",
            type=int,
            default=0,
            help="Wall-clock budget per monitor (defaults to CRAWL_MAX_SECONDS).",
        )

    def handle(self, *args, **options):
        monitors = list(Monitor.objects.filter(is_active=True, kind="broken_links").order_by("last_checked_at"))
        if not options["force"]:
            monitors = [monitor for monitor in monitors if should_check(monitor)]
        if options["limit"] and options["limit"] > 0:
            monitors = monitors[: options["limit"]]

        budget = options["max_seconds"] or settings.CRAWL_MAX_SECONDS
        crawls = 0
        for monitor in monitors:
            try:
                summary = crawl_monitor(monitor, max_seconds=budget)
            except ValueError as exc:
                self.stdout.write(self.style.WARNING(f"{monitor.name}: skipped ({exc})"))
                continue
            crawls += 1
            self.stdout.write(
                f"{monitor.name}: {summary['pages_crawled']} page(s), "
                f"{summary['links_checked']} link(s), "
                f"{summary['broken_count']} broken ({summary['new_count']} new)"
                + (f" — {summary['error']}" if summary.get("error") else "")
            )

        self.stdout.write(self.style.SUCCESS(f"Crawled {crawls} monitor(s)."))
