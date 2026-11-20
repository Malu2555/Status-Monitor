"""Phase 2 features: multi-region reporting, TLS state, custom status pages."""
import json
from typing import Any

from django.test import TestCase

from .models import Check, Monitor, StatusPage


class Phase2ApiTests(TestCase):
    def setUp(self):
        resp = self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {"username": "p2user", "email": "p2@example.com", "password": "Str0ng-Pass!", "accepted_tos": True, "accepted_age": True}
            ),
            content_type="application/json",
        )
        self.access = resp.json()["access"]
        self.user_id = resp.json()["user"]["id"]
        self.monitor = Monitor.objects.create(
            name="Site", url="https://example.com", owner_id=self.user_id
        )

    def _auth(self) -> dict[str, Any]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.access}"}

    def test_regions_endpoint_reports_per_region(self):
        Check.objects.create(
            monitor=self.monitor, is_up=True, status_code=200, response_ms=12, region="eu-west"
        )
        Check.objects.create(
            monitor=self.monitor, is_up=False, status_code=503, response_ms=20, region="us-east"
        )
        resp = self.client.get(f"/api/monitors/{self.monitor.pk}/regions", **self._auth())
        self.assertEqual(resp.status_code, 200)
        regions = {row["region"]: row for row in resp.json()}
        self.assertEqual(regions["eu-west"]["last_status"], "up")
        self.assertEqual(regions["us-east"]["last_status"], "down")

    def test_ssl_endpoint_before_first_check(self):
        resp = self.client.get(f"/api/monitors/{self.monitor.pk}/ssl", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Not checked yet", resp.json()["error"])

    def test_status_page_public_and_404(self):
        Monitor.objects.filter(pk=self.monitor.pk).update(last_status="up")
        page = StatusPage.objects.create(
            slug="acme", title="Acme Status", description="All systems", theme_color="#123456"
        )
        page.monitors.add(self.monitor)
        resp = self.client.get("/api/public/statuspages/acme")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["title"], "Acme Status")
        self.assertEqual(len(body["monitors"]), 1)
        self.assertEqual(self.client.get("/api/public/statuspages/missing").status_code, 404)

    def test_status_page_hidden_when_not_public(self):
        StatusPage.objects.create(slug="hidden", title="Hidden", is_public=False)
        self.assertEqual(self.client.get("/api/public/statuspages/hidden").status_code, 404)
