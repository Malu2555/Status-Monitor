"""Monitor API + check-engine tests."""

import json
from typing import Any
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from .models import Check, Monitor
from .services import run_check


class FakeResponse:
    status_code = 200
    headers = {}


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def get(self, url, headers=None):
        return FakeResponse()


class MonitorApiTests(TestCase):
    def setUp(self):
        resp = self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "username": "monuser",
                    "email": "mon@example.com",
                    "password": "Str0ng-Pass!",
                    "accepted_tos": True,
                    "accepted_age": True,
                }
            ),
            content_type="application/json",
        )
        self.access = resp.json()["access"]

    def _auth(self) -> dict[str, Any]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.access}"}

    def _create(self, payload):
        return self.client.post(
            "/api/monitors",
            data=json.dumps(payload),
            content_type="application/json",
            **self._auth(),
        )

    def test_create_and_list(self):
        resp = self._create({"name": "My Site", "url": "https://example.com", "is_public": True})
        self.assertEqual(resp.status_code, 201)
        monitor_id = resp.json()["id"]
        resp = self.client.get("/api/monitors", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], monitor_id)
        self.assertEqual(body[0]["last_status"], "unknown")

    def test_ssrf_urls_rejected(self):
        resp = self._create({"name": "Bad", "url": "http://127.0.0.1:8000/admin/"})
        self.assertEqual(resp.status_code, 422)
        resp = self._create({"name": "Bad2", "url": "ftp://example.com/file"})
        self.assertEqual(resp.status_code, 422)
        resp = self._create({"name": "Bad3", "url": "http://169.254.169.254/latest/meta-data"})
        self.assertEqual(resp.status_code, 422)

    def test_free_plan_limit(self):
        self._create({"name": "A", "url": "https://example.com"})
        resp = self._create({"name": "B", "url": "https://example.org"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("limit", resp.json()["detail"].lower())

    def test_public_list_excludes_private_and_inactive(self):
        created = self._create({"name": "Site", "url": "https://example.com", "is_public": True}).json()
        resp = self.client.get("/api/public/monitors")
        self.assertIn(created["id"], [m["id"] for m in resp.json()])
        # hide it
        self.client.patch(
            f"/api/monitors/{created['id']}",
            data=json.dumps({"is_public": False}),
            content_type="application/json",
            **self._auth(),
        )
        resp = self.client.get("/api/public/monitors")
        self.assertNotIn(created["id"], [m["id"] for m in resp.json()])

    def test_ownership_isolation(self):
        created = self._create({"name": "Mine", "url": "https://example.com"}).json()
        # second user must not see or touch it
        self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "username": "other",
                    "email": "other@example.com",
                    "password": "Str0ng-Pass!",
                    "accepted_tos": True,
                    "accepted_age": True,
                }
            ),
            content_type="application/json",
        )
        resp = self.client.get(f"/api/monitors/{created['id']}")
        self.assertEqual(resp.status_code, 401)  # no token at all
        resp = self.client.delete(f"/api/monitors/{created['id']}")
        self.assertEqual(resp.status_code, 401)

    def test_run_check_records_result(self):
        created = self._create({"name": "Site", "url": "https://example.com"}).json()
        monitor = Monitor.objects.get(pk=created["id"])
        with (
            patch("monitors.services.httpx.Client", FakeClient),
            patch("monitors.services.validate_target_url", side_effect=lambda url: url),
        ):
            result = run_check(monitor)
        self.assertTrue(result["is_up"])
        monitor.refresh_from_db()
        self.assertEqual(monitor.last_status, Monitor.Status.UP)
        self.assertEqual(Check.objects.filter(monitor=monitor).count(), 1)

    def test_run_checks_command(self):
        created = self._create({"name": "Site", "url": "https://example.com"}).json()
        with (
            patch("monitors.services.httpx.Client", FakeClient),
            patch("monitors.services.validate_target_url", side_effect=lambda url: url),
        ):
            call_command("run_checks")
        monitor = Monitor.objects.get(pk=created["id"])
        self.assertEqual(monitor.last_status, Monitor.Status.UP)
