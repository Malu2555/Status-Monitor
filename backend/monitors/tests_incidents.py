"""Incident history endpoint used by the dashboard timeline."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from accounts.services import create_access_token
from monitors.models import Incident, Monitor


class IncidentHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hist", "hist@example.com", "Str0ng-Pass!")
        self.monitor = Monitor.objects.create(owner=self.user, name="Site", url="https://example.com")
        self.access = create_access_token(self.user)
        self.auth = {"Authorization": f"Bearer {self.access}"}
        now = timezone.now()
        for index in range(3):
            Incident.objects.create(
                monitor=self.monitor,
                started_at=now - timedelta(hours=index + 1),
                ended_at=now - timedelta(hours=index, minutes=30),
                checks_down=index + 1,
                last_status_code=503,
                postmortem="draft" if index == 0 else "",
            )

    def _get(self, **params):
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = f"/api/monitors/{self.monitor.pk}/incidents"
        return self.client.get(f"{url}?{query}" if query else url, headers=self.auth)

    def test_returns_newest_first(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["postmortem"], "draft")
        self.assertGreater(rows[0]["started_at"], rows[1]["started_at"])

    def test_limit_and_offset_page_the_history(self):
        first_page = self._get(limit=2).json()
        self.assertEqual(len(first_page), 2)
        second_page = self._get(limit=2, offset=2).json()
        self.assertEqual(len(second_page), 1)
        self.assertNotEqual(first_page[0]["id"], second_page[0]["id"])

    def test_other_user_cannot_read_the_history(self):
        stranger = User.objects.create_user("nope", "nope@example.com", "Str0ng-Pass!")
        token = create_access_token(stranger)
        resp = self.client.get(
            f"/api/monitors/{self.monitor.pk}/incidents",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, 404)
