from unittest import mock

from django.test import TestCase, override_settings


class HealthEndpointTests(TestCase):
    def get(self):
        return self.client.get("/api/health")

    def test_health_ok(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["db"], "ok")
        self.assertEqual(body["cache"], "ok")

    @override_settings(HEALTH_VERBOSE=True)
    def test_health_db_down(self):
        with mock.patch("health.api._database_ok", return_value=(False, "RuntimeError: db down")):
            response = self.get()
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["db"], "err")
        self.assertIn("RuntimeError", body["details"]["db"])

    @override_settings(HEALTH_VERBOSE=True)
    def test_health_cache_down(self):
        with mock.patch("health.api._cache_ok", return_value=(False, "RuntimeError: cache down")):
            response = self.get()
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["cache"], "err")
        self.assertIn("RuntimeError", body["details"]["cache"])

    @override_settings(HEALTH_VERBOSE=False)
    def test_failure_details_are_hidden_in_production(self):
        with mock.patch("health.api._database_ok", return_value=(False, "OperationalError: secret-host")):
            response = self.get()
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["db"], "err")
        self.assertNotIn("details", body)
        self.assertNotIn("secret-host", response.content.decode())
