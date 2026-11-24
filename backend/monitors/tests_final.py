"""Final-stage features: API tokens, badges, CSV export, heartbeats, status pages."""

import json
from datetime import timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone

from monitors.models import Monitor, StatusPage
from monitors.services import evaluate_heartbeat


class _AuthMixin:
    client: Any

    def setUp(self):
        resp = self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "username": "finaluser",
                    "email": "final@example.com",
                    "password": "Str0ng-Pass!",
                    "accepted_tos": True,
                    "accepted_age": True,
                }
            ),
            content_type="application/json",
        )
        body = resp.json()
        self.access = body["access"]
        self.user_id = body["user"]["id"]

    def _auth(self) -> dict[str, Any]:
        return {"Authorization": f"Bearer {self.access}"}


class ApiTokenTests(_AuthMixin, TestCase):
    def _create_token(self, scope="write"):
        resp = self.client.post(
            "/api/auth/tokens",
            data=json.dumps({"name": "ci", "scope": scope}),
            content_type="application/json",
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_token_create_and_use(self):
        created = self._create_token("write")
        self.assertTrue(created["token"].startswith("sm_"))
        resp = self.client.get("/api/monitors", HTTP_X_API_KEY=created["token"])
        self.assertEqual(resp.status_code, 200)

    def test_read_only_token_cannot_write(self):
        created = self._create_token("read")
        resp = self.client.post(
            "/api/monitors",
            data=json.dumps({"name": "Site", "url": "https://example.com"}),
            content_type="application/json",
            HTTP_X_API_KEY=created["token"],
        )
        self.assertEqual(resp.status_code, 403)

    def test_revoked_token_rejected(self):
        created = self._create_token("write")
        revoke = self.client.delete(f"/api/auth/tokens/{created['id']}", headers=self._auth())
        self.assertEqual(revoke.status_code, 200)
        resp = self.client.get("/api/monitors", HTTP_X_API_KEY=created["token"])
        self.assertEqual(resp.status_code, 401)

    def test_list_tokens(self):
        self._create_token("write")
        resp = self.client.get("/api/auth/tokens", headers=self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertNotIn("token", resp.json()[0])


class BadgeAndExportTests(_AuthMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.monitor = Monitor.objects.create(
            name="Badge Site",
            url="https://example.com",
            owner_id=self.user_id,
            is_public=True,
            last_status="up",
        )

    def test_badge_svg(self):
        resp = self.client.get(f"/api/public/badge/{self.monitor.pk}.svg")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("image/svg+xml", resp["Content-Type"])
        self.assertIn("operational", resp.content.decode())

    def test_csv_export(self):
        resp = self.client.get("/api/monitors/export.csv", headers=self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        text = resp.content.decode()
        self.assertIn("monitor,kind,url,last_status", text)
        self.assertIn("Badge Site", text)


class HeartbeatTests(_AuthMixin, TestCase):
    def test_heartbeat_create_ping_and_miss(self):
        resp = self.client.post(
            "/api/monitors",
            data=json.dumps(
                {
                    "name": "Cron",
                    "kind": "heartbeat",
                    "check_interval_seconds": 300,
                    "heartbeat_grace_seconds": 60,
                }
            ),
            content_type="application/json",
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["kind"], "heartbeat")
        token = body["heartbeat_token"]
        self.assertTrue(token)

        # Inbound ping flips it up.
        self.assertEqual(self.client.post(f"/api/public/heartbeat/{token}").status_code, 200)
        monitor = Monitor.objects.get(pk=body["id"])
        self.assertEqual(monitor.last_status, Monitor.Status.UP)

        # Age the last ping beyond interval+grace, then evaluate -> down.
        Monitor.objects.filter(pk=monitor.pk).update(last_ping_at=timezone.now() - timedelta(seconds=400))
        monitor.refresh_from_db()
        result = evaluate_heartbeat(monitor)
        self.assertFalse(result["is_up"])
        monitor.refresh_from_db()
        self.assertEqual(monitor.last_status, Monitor.Status.DOWN)


class StatusPageCrudTests(_AuthMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.monitor = Monitor.objects.create(name="Site", url="https://example.com", owner_id=self.user_id)

    def test_crud(self):
        payload = {"slug": "acme", "title": "Acme", "monitor_ids": [self.monitor.pk]}
        resp = self.client.post(
            "/api/statuspages",
            data=json.dumps(payload),
            content_type="application/json",
            headers=self._auth(),
        )
        self.assertEqual(resp.status_code, 201)
        page_id = resp.json()["id"]
        self.assertEqual(resp.json()["monitor_ids"], [self.monitor.pk])

        resp = self.client.get("/api/statuspages", headers=self._auth())
        self.assertEqual(resp.json()[0]["slug"], "acme")

        resp = self.client.patch(
            f"/api/statuspages/{page_id}",
            data=json.dumps({"title": "Acme Status"}),
            content_type="application/json",
            headers=self._auth(),
        )
        self.assertEqual(resp.json()["title"], "Acme Status")

        self.assertEqual(self.client.delete(f"/api/statuspages/{page_id}", headers=self._auth()).status_code, 204)
        self.assertFalse(StatusPage.objects.filter(pk=page_id).exists())
