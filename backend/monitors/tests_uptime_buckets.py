"""Tests for the per-bucket uptime series endpoint used by the monitor detail page."""
import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from monitors.models import Check, Monitor


class UptimeBucketsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ubuser", email="ub@example.com", password="CorrectHorse1"
        )
        self.monitor = Monitor.objects.create(
            owner=self.user, name="UB", url="https://example.com", kind="http"
        )
        now = timezone.now()
        for i in range(6):
            Check.objects.create(
                monitor=self.monitor,
                is_up=i % 2 == 0,
                response_ms=100 + i,
                region="local",
                checked_at=now - timedelta(hours=i),
            )

    def _token(self):
        resp = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "ubuser", "password": "CorrectHorse1"}),
            content_type="application/json",
        )
        return resp.json()["access"]

    def test_uptime_buckets_shape(self):
        token = self._token()
        resp = self.client.get(
            f"/api/monitors/{self.monitor.pk}/uptime-buckets?hours=24&bucket_hours=1",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("bucket", row)
            self.assertIn("up_ratio", row)
            self.assertIn("samples", row)
            self.assertGreaterEqual(row["up_ratio"], 0.0)
            self.assertLessEqual(row["up_ratio"], 1.0)
        # The window is contiguous: 25 hourly buckets for a 24h span.
        self.assertEqual(len(rows), 25)

    def test_uptime_buckets_requires_auth(self):
        resp = self.client.get(f"/api/monitors/{self.monitor.pk}/uptime-buckets")
        self.assertEqual(resp.status_code, 401)
