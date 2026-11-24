"""Superuser-only HTTP triggers for the periodic management commands."""

from django.test import TestCase

from accounts.models import User
from accounts.services import create_access_token
from audit.models import AuditLogEntry
from monitors.models import Monitor


class AdminRunTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            "ops",
            "ops@example.com",
            "Str0ng-Pass!",
            is_staff=True,
            is_superuser=True,
        )
        self.user = User.objects.create_user("plain", "plain@example.com", "Str0ng-Pass!")
        self.staff_token = create_access_token(self.staff)
        self.user_token = create_access_token(self.user)
        # Keep the sweep off the network: no due monitors, no TLS handshakes.
        Monitor.objects.update(is_active=False)

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_index_lists_the_periodic_jobs(self):
        resp = self.client.get("/api/admin/run", headers=self._auth(self.staff_token))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            {job["name"] for job in resp.json()},
            {
                "run-checks",
                "deliver-notifications",
                "check-ssl",
                "check-domains",
                "crawl-links",
            },
        )

    def test_index_requires_staff(self):
        self.assertEqual(self.client.get("/api/admin/run").status_code, 401)
        resp = self.client.get("/api/admin/run", headers=self._auth(self.user_token))
        self.assertEqual(resp.status_code, 403)

    def test_non_staff_cannot_trigger_jobs(self):
        for path in (
            "run-checks",
            "deliver-notifications",
            "check-ssl",
            "check-domains",
            "crawl-links",
        ):
            resp = self.client.post(f"/api/admin/run/{path}", headers=self._auth(self.user_token))
            self.assertEqual(resp.status_code, 403, path)

    def test_run_checks_returns_output_and_audits(self):
        resp = self.client.post("/api/admin/run/run-checks", headers=self._auth(self.staff_token))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["job"], "run-checks")
        self.assertIn("Checked 0 monitor", body["output"])
        self.assertTrue(AuditLogEntry.objects.filter(kind="admin.run_job").exists())

    def test_deliver_notifications_reports_counts(self):
        resp = self.client.post("/api/admin/run/deliver-notifications", headers=self._auth(self.staff_token))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("sent=0", resp.json()["output"])

    def test_check_ssl_runs(self):
        resp = self.client.post("/api/admin/run/check-ssl", headers=self._auth(self.staff_token))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("certificate", resp.json()["output"])
