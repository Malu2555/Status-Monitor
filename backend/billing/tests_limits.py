"""Capacity gates for the hosted tiers.

Paid plans only raise *caps* (monitors, check frequency, status pages, alert
channels, history window); they never unlock features. These tests pin the caps
themselves and prove the create endpoints enforce them.
"""
import json

from django.test import TestCase

from accounts.models import User
from accounts.services import create_access_token
from billing.models import Subscription
from billing.services import (
    can_add_channel,
    can_add_status_page,
    channels_limit,
    history_days,
    status_pages_limit,
)
from monitors.models import Monitor, StatusPage
from notifications.models import MonitorNotificationChannel


class PlanCapacityTests(TestCase):
    def test_free_caps(self):
        user = User.objects.create_user("freeuser", "free@example.com", "Str0ng-Pass!")
        self.assertEqual(status_pages_limit(user), 1)
        self.assertEqual(channels_limit(user), 2)
        self.assertEqual(history_days(user), 30)

        self.assertTrue(can_add_status_page(user)[0])
        StatusPage.objects.create(owner=user, slug="free-page", title="Free")
        ok, reason = can_add_status_page(user)
        self.assertFalse(ok)
        self.assertIn("1/1 status pages", reason)

        monitor = Monitor.objects.create(owner=user, name="Site", url="https://example.com")
        for index in range(2):
            MonitorNotificationChannel.objects.create(
                user=user, monitor=monitor, kind="email", address=f"free{index}@example.com"
            )
        ok, reason = can_add_channel(user)
        self.assertFalse(ok)
        self.assertIn("2/2 notification channels", reason)

    def test_pro_raises_caps(self):
        user = User.objects.create_user("prouser", "pro@example.com", "Str0ng-Pass!")
        Subscription.objects.create(user=user, plan="pro", status="active")
        self.assertEqual(status_pages_limit(user), 3)
        self.assertEqual(channels_limit(user), 10)
        self.assertEqual(history_days(user), 90)

        for index in range(3):
            StatusPage.objects.create(owner=user, slug=f"pro-{index}", title=f"P{index}")
        self.assertFalse(can_add_status_page(user)[0])

    def test_business_is_unlimited(self):
        user = User.objects.create_user("bizuser", "biz@example.com", "Str0ng-Pass!")
        Subscription.objects.create(user=user, plan="business", status="active")
        self.assertIsNone(status_pages_limit(user))
        self.assertIsNone(channels_limit(user))
        self.assertEqual(history_days(user), 365)

        for index in range(5):
            StatusPage.objects.create(owner=user, slug=f"biz-{index}", title=f"B{index}")
        self.assertTrue(can_add_status_page(user)[0])


class CapacityEnforcementApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("capuser", "cap@example.com", "Str0ng-Pass!")
        self.auth = {"Authorization": f"Bearer {create_access_token(self.user)}"}

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            headers=self.auth,
        )

    def test_status_page_cap_is_enforced(self):
        first = self._post("/api/statuspages", {"slug": "one", "title": "One"})
        self.assertEqual(first.status_code, 201)
        second = self._post("/api/statuspages", {"slug": "two", "title": "Two"})
        self.assertEqual(second.status_code, 400)
        self.assertIn("status pages", second.json()["detail"])

    def test_channel_cap_is_enforced(self):
        monitor = Monitor.objects.create(owner=self.user, name="Site", url="https://example.com")
        for index in range(2):
            created = self._post(
                "/api/notifications/channels",
                {"monitor_id": monitor.pk, "kind": "telegram", "address": f"token{index}|chat{index}"},
            )
            self.assertEqual(created.status_code, 201)
        blocked = self._post(
            "/api/notifications/channels",
            {"monitor_id": monitor.pk, "kind": "telegram", "address": "token9|chat9"},
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("notification channels", blocked.json()["detail"])
