"""Tests for the dashboard overview aggregate endpoint."""
import json

from django.test import TestCase

from accounts.models import User
from monitors.models import Check, Monitor


class OverviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="oveuser", email="ove@example.com", password="CorrectHorse1"
        )
        self.monitor = Monitor.objects.create(
            owner=self.user, name="OV", url="https://example.com", kind="http"
        )
        Check.objects.create(monitor=self.monitor, is_up=True, response_ms=100, region="local")

    def _token(self):
        resp = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "oveuser", "password": "CorrectHorse1"}),
            content_type="application/json",
        )
        return resp.json()["access"]

    def test_overview_aggregate(self):
        token = self._token()
        resp = self.client.get("/api/monitors/overview", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["monitors_total"], 1)
        self.assertEqual(body["monitors_unknown"], 1)  # no check has flipped status yet
        self.assertEqual(len(body["checks"]), 1)
        self.assertEqual(body["checks"][0]["name"], "OV")

    def test_overview_requires_auth(self):
        self.assertEqual(self.client.get("/api/monitors/overview").status_code, 401)
