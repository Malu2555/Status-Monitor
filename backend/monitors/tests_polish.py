"""Product-polish tests: incidents, maintenance windows, list pagination."""
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from accounts.services import create_access_token
from notifications.models import MonitorNotificationChannel, NotificationDelivery

from .models import Incident, MaintenanceWindow, Monitor


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}


class FakeClient:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def get(self, url, headers=None):
        return FakeResponse(self.status_code)


class IncidentTests(TestCase):
    def setUp(self):
        from .services import run_check

        self.run_check = run_check
        self.user = User.objects.create_user("polish", "p@example.com", "password123")
        self.monitor = Monitor.objects.create(
            owner=self.user,
            name="Site",
            url="https://example.com",
            last_status=Monitor.Status.UP,
        )
        MonitorNotificationChannel.objects.create(
            user=self.user, monitor=self.monitor, kind="email", address="ops@example.com"
        )

    def _check(self, status_code):
        with patch("monitors.services.httpx.Client", lambda **kw: FakeClient(status_code)), patch(
            "monitors.services.validate_target_url", side_effect=lambda url: url
        ):
            return self.run_check(self.monitor)

    def test_down_then_up_opens_and_closes_incident(self):
        self.assertFalse(self._check(500)["is_up"])
        incident = Incident.objects.get()
        self.assertIsNone(incident.ended_at)
        self.assertTrue(self._check(200)["is_up"])
        incident.refresh_from_db()
        self.assertIsNotNone(incident.ended_at)
        self.assertFalse(Incident.objects.filter(ended_at=None).exists())

    def test_consecutive_down_checks_increment_counter(self):
        self._check(500)  # UP → DOWN transition opens the incident
        self._check(500)  # DOWN → DOWN increments the open incident
        incident = Incident.objects.get()
        self.assertEqual(incident.checks_down, 2)

    def test_down_during_maintenance_suppresses_alert(self):
        now = timezone.now()
        MaintenanceWindow.objects.create(
            monitor=self.monitor,
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            note="reboot",
        )
        self.assertFalse(self._check(500)["is_up"])
        self.assertEqual(NotificationDelivery.objects.filter(monitor=self.monitor).count(), 0)
        self.assertTrue(Incident.objects.filter(ended_at=None).exists())

    def test_down_outside_maintenance_alerts(self):
        now = timezone.now()
        MaintenanceWindow.objects.create(
            monitor=self.monitor,
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
            note="future work",
        )
        self.assertFalse(self._check(500)["is_up"])
        self.assertEqual(NotificationDelivery.objects.filter(monitor=self.monitor).count(), 1)


class ListPolishTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pager", "pg@example.com", "password123")
        self.access = create_access_token(self.user)
        self.hdr: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {self.access}"}
        for index in range(5):
            Monitor.objects.create(
                owner=self.user,
                name=f"Site {chr(65 + index)}",
                url=f"https://e{index}.example.com",
                last_status=Monitor.Status.UP if index % 2 == 0 else Monitor.Status.DOWN,
            )

    def test_limit_and_offset_and_backward_compat(self):
        response = self.client.get("/api/monitors?limit=2", **self.hdr)
        self.assertEqual(len(response.json()), 2)
        response = self.client.get("/api/monitors?limit=2&offset=2", **self.hdr)
        self.assertEqual(len(response.json()), 2)
        response = self.client.get("/api/monitors", **self.hdr)
        self.assertEqual(len(response.json()), 5)

    def test_filter_and_sort(self):
        response = self.client.get("/api/monitors?status=down", **self.hdr)
        self.assertEqual(len(response.json()), 2)
        response = self.client.get("/api/monitors?sort=name", **self.hdr)
        names = [monitor["name"] for monitor in response.json()]
        self.assertEqual(names, sorted(names))

    def test_public_maintenance_endpoint(self):
        now = timezone.now()
        monitor = Monitor.objects.get(name="Site A")
        MaintenanceWindow.objects.create(
            monitor=monitor,
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=55),
            note="planned",
        )
        response = self.client.get("/api/public/maintenance")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["monitor_name"], "Site A")
        self.assertEqual(body[0]["note"], "planned")

    def test_public_detail_has_incidents_and_uptime_30d(self):
        monitor = Monitor.objects.get(name="Site A")
        Incident.objects.create(monitor=monitor, started_at=timezone.now(), checks_down=3)
        response = self.client.get(f"/api/public/monitors/{monitor.pk}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("uptime_30d", body)
        self.assertEqual(len(body["incidents"]), 1)
        self.assertEqual(body["incidents"][0]["checks_down"], 3)
