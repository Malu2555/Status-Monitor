"""Retention housekeeping: raw checks and expired blocks are pruned."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import BlockedIP, User
from monitors.models import Check, Monitor


class PruneHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pruneuser", "p@example.com", "Str0ng-Pass!")
        self.monitor = Monitor.objects.create(owner=self.user, name="Site", url="https://example.com")
        self.old_check = Check.objects.create(monitor=self.monitor, is_up=True)
        self.new_check = Check.objects.create(monitor=self.monitor, is_up=True)
        Check.objects.filter(pk=self.old_check.pk).update(checked_at=timezone.now() - timedelta(days=40))
        self.expired_block = BlockedIP.objects.create(
            ip="203.0.113.9",
            reason="old",
            expires_at=timezone.now() - timedelta(hours=1),
        )

    def test_dry_run_keeps_data(self):
        out = StringIO()
        call_command("prune_history", "--days", "30", "--dry-run", stdout=out)
        self.assertIn("[dry-run]", out.getvalue())
        self.assertTrue(Check.objects.filter(pk=self.old_check.pk).exists())
        self.assertTrue(BlockedIP.objects.filter(pk=self.expired_block.pk).exists())

    def test_prunes_old_checks_and_expired_blocks(self):
        out = StringIO()
        call_command("prune_history", "--days", "30", stdout=out)
        self.assertFalse(Check.objects.filter(pk=self.old_check.pk).exists())
        self.assertTrue(Check.objects.filter(pk=self.new_check.pk).exists())
        self.assertFalse(BlockedIP.objects.filter(pk=self.expired_block.pk).exists())
        self.assertIn("checks older than 30d", out.getvalue())
