"""The `moderate` management command (routine admin without the admin UI)."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import BlockedIP, User
from monitors.models import Monitor


class ModerateCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", "alice@example.com", "Str0ng-Pass!")
        self.monitor = Monitor.objects.create(owner=self.user, name="Site", url="https://example.com")

    def test_disable_and_enable_user(self):
        out = StringIO()
        call_command(
            "moderate",
            "disable_user",
            "alice@example.com",
            "--reason",
            "tos_violation",
            stdout=out,
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.monitor.refresh_from_db()
        self.assertFalse(self.monitor.is_active)
        self.assertIn("Disabled alice", out.getvalue())

        call_command("moderate", "enable_user", "alice", stdout=StringIO())
        self.user.refresh_from_db()
        self.monitor.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.monitor.is_active)

    def test_block_and_unblock_ip(self):
        call_command("moderate", "block_ip", "203.0.113.9", "--hours", "1", stdout=StringIO())
        self.assertTrue(BlockedIP.objects.filter(ip="203.0.113.9").exists())
        call_command("moderate", "unblock_ip", "203.0.113.9", stdout=StringIO())
        self.assertFalse(BlockedIP.objects.filter(ip="203.0.113.9").exists())

    def test_list_recent_runs(self):
        out = StringIO()
        call_command("moderate", "list_recent", "--days", "7", stdout=out)
        self.assertIn("Blocked IPs", out.getvalue())
        self.assertIn("Privileged accounts", out.getvalue())
