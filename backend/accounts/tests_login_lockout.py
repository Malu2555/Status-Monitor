"""Per-username login lockout (independent of the shared-client-IP bucket)."""

import json

from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.models import User


@override_settings(LOGIN_MAX_FAILURES=3, LOGIN_LOCK_WINDOW=60, LOGIN_LOCK_SECONDS=60)
class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice", "alice@example.com", "Str0ng-Pass!")

    def _login(self, password: str):
        return self.client.post(
            "/api/auth/login",
            json.dumps({"username": "alice", "password": password}),
            content_type="application/json",
        )

    def test_lockout_after_repeated_failures(self):
        for _ in range(3):
            self.assertEqual(self._login("wrong-password").status_code, 401)
        response = self._login("Str0ng-Pass!")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Too many failed attempts", response.json()["detail"])

    def test_successful_login_clears_the_failure_streak(self):
        self.assertEqual(self._login("wrong-password").status_code, 401)
        self.assertEqual(self._login("wrong-password").status_code, 401)
        self.assertEqual(self._login("Str0ng-Pass!").status_code, 200)
        self.assertEqual(self._login("wrong-password").status_code, 401)
        # Would be locked if the two earlier failures had not been cleared.
        self.assertEqual(self._login("Str0ng-Pass!").status_code, 200)

    def test_debug_proxy_resolves_a_sample_chain(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with override_settings(TRUSTED_PROXY_IPS=["*"], PROXY_HOPS=2):
            call_command(
                "debug_proxy",
                "--remote",
                "10.0.0.1",
                "--xff",
                "6.6.6.6, 1.2.3.4, 10.0.0.1",
                stdout=out,
            )
        self.assertIn("PROXY_HOPS=2", out.getvalue())
        self.assertIn("client_ip='1.2.3.4'", out.getvalue())
