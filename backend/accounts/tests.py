import json

from django.conf import settings
from django.test import TestCase


class AuthFlowTests(TestCase):
    def _register(self, username="alice", email="alice@example.com", password="Str0ng-Pass!"):
        return self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "username": username,
                    "email": email,
                    "password": password,
                    "accepted_tos": True,
                    "accepted_age": True,
                }
            ),
            content_type="application/json",
        )

    def _login(self, username="alice", password="Str0ng-Pass!"):
        return self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )

    def _csrf_header(self):
        return {"X-CSRF-Token": self.client.cookies[settings.COOKIE_CSRF_NAME].value}

    def test_register_sets_cookies_and_token(self):
        resp = self._register()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIn("access", body)
        self.assertEqual(body["user"]["username"], "alice")
        self.assertEqual(body["user"]["plan"], "free")
        self.assertIn(settings.COOKIE_REFRESH_NAME, self.client.cookies)

    def test_duplicate_email_and_username_rejected(self):
        self._register()
        resp = self._register(username="bob", email="alice@example.com")
        self.assertEqual(resp.status_code, 400)
        resp = self._register(username="alice", email="other@example.com")
        self.assertEqual(resp.status_code, 400)

    def test_login_wrong_password(self):
        self._register()
        resp = self._login(password="Wrong-Pass!")
        self.assertEqual(resp.status_code, 401)

    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_login_then_me(self):
        self._register()
        resp = self._login()
        self.assertEqual(resp.status_code, 200)
        access = resp.json()["access"]
        resp = self.client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "alice")

    def test_refresh_requires_csrf_token(self):
        self._register()
        resp = self.client.post("/api/auth/refresh")
        self.assertEqual(resp.status_code, 403)

    def test_refresh_rotates_and_revokes_old_token(self):
        self._register()
        old_refresh = self.client.cookies[settings.COOKIE_REFRESH_NAME].value
        resp = self.client.post("/api/auth/refresh", headers=self._csrf_header())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())
        new_refresh = self.client.cookies[settings.COOKIE_REFRESH_NAME].value
        self.assertNotEqual(old_refresh, new_refresh)
        # Replaying the rotated-out refresh token must fail.
        self.client.cookies[settings.COOKIE_REFRESH_NAME] = old_refresh
        resp = self.client.post("/api/auth/refresh", headers=self._csrf_header())
        self.assertEqual(resp.status_code, 401)

    def test_logout_revokes_refresh(self):
        resp = self._register()
        access = resp.json()["access"]
        resp = self.client.post("/api/auth/logout", HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post("/api/auth/refresh", headers=self._csrf_header())
        self.assertEqual(resp.status_code, 401)
