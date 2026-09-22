from unittest import mock

from django.test import TestCase


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

    def test_health_db_down(self):
        with mock.patch("health.api._database_ok", return_value=(False, "RuntimeError: db down")):
            response = self.get()
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["db"], "err")
        self.assertIn("RuntimeError", body["details"]["db"])

    def test_health_cache_down(self):
        with mock.patch("health.api._cache_ok", return_value=(False, "RuntimeError: cache down")):
            response = self.get()
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["cache"], "err")
        self.assertIn("RuntimeError", body["details"]["cache"])
