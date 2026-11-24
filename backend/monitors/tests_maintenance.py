"""Maintenance window planning API."""

import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from accounts.services import create_access_token
from monitors.models import MaintenanceWindow, Monitor


class MaintenanceApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plan", "plan@example.com", "Str0ng-Pass!")
        self.other = User.objects.create_user("other", "other@example.com", "Str0ng-Pass!")
        self.monitor = Monitor.objects.create(owner=self.user, name="Site", url="https://example.com")
        self.access = create_access_token(self.user)
        self.auth = {"Authorization": f"Bearer {self.access}"}

    def _create(self, monitor_id=None, days_ahead=1, hours=1, note="deploy"):
        start = timezone.now() + timedelta(days=days_ahead)
        return self.client.post(
            f"/api/monitors/{monitor_id or self.monitor.pk}/maintenance",
            data=json.dumps(
                {
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(hours=hours)).isoformat(),
                    "note": note,
                }
            ),
            content_type="application/json",
            headers=self.auth,
        )

    def test_create_and_list_window(self):
        resp = self._create()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["monitor_id"], self.monitor.pk)
        self.assertEqual(body["note"], "deploy")

        listed = self.client.get(f"/api/monitors/{self.monitor.pk}/maintenance", headers=self.auth)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

    def test_overlapping_window_is_rejected(self):
        self.assertEqual(self._create().status_code, 201)
        self.assertEqual(self._create(note="again").status_code, 422)

    def test_ends_before_starts_is_rejected(self):
        start = timezone.now() + timedelta(days=1)
        resp = self.client.post(
            f"/api/monitors/{self.monitor.pk}/maintenance",
            data=json.dumps(
                {
                    "starts_at": start.isoformat(),
                    "ends_at": (start - timedelta(hours=1)).isoformat(),
                }
            ),
            content_type="application/json",
            headers=self.auth,
        )
        self.assertEqual(resp.status_code, 422)

    def test_future_window_can_be_deleted(self):
        window_id = self._create().json()["id"]
        resp = self.client.delete(f"/api/monitors/{self.monitor.pk}/maintenance/{window_id}", headers=self.auth)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(MaintenanceWindow.objects.exists())

    def test_started_window_cannot_be_deleted(self):
        window = MaintenanceWindow.objects.create(
            monitor=self.monitor,
            starts_at=timezone.now() - timedelta(minutes=5),
            ends_at=timezone.now() + timedelta(hours=1),
        )
        resp = self.client.delete(f"/api/monitors/{self.monitor.pk}/maintenance/{window.pk}", headers=self.auth)
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(MaintenanceWindow.objects.filter(pk=window.pk).exists())

    def test_other_users_monitor_is_not_found(self):
        resp = self._create(monitor_id=self.monitor.pk + 999)
        self.assertEqual(resp.status_code, 404)
