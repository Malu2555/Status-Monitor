"""Terms-of-service consent + staff moderation (disable/enable)."""
import json

from django.conf import settings
from django.test import TestCase

from accounts.models import User
from accounts.services import create_access_token
from audit.models import AuditLogEntry
from monitors.models import Monitor


class PolicyConsentTests(TestCase):
    def _register(self, **overrides):
        payload = {
            "username": "consent1",
            "email": "consent1@example.com",
            "password": "Str0ng-Pass!",
            "accepted_tos": True,
            "accepted_age": True,
            **overrides,
        }
        return self.client.post(
            "/api/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_register_requires_both_consent_flags(self):
        for overrides in (
            {"accepted_tos": False},
            {"accepted_age": False},
            {"accepted_tos": False, "accepted_age": False},
        ):
            resp = self._register(**overrides)
            self.assertEqual(resp.status_code, 400, overrides)
        self.assertFalse(User.objects.exists())

    def test_register_stamps_consent_version(self):
        resp = self._register()
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(username="consent1")
        self.assertIsNotNone(user.tos_accepted_at)
        self.assertIsNotNone(user.age_confirmed_at)
        self.assertEqual(user.tos_version, settings.TOS_VERSION)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                kind="auth.register", payload__tos_version=settings.TOS_VERSION
            ).exists()
        )

    def test_terms_endpoint_serves_seeded_text(self):
        resp = self.client.get("/api/policies/terms")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["slug"], "terms")
        self.assertIn("Terms of Service", body["title"])
        self.assertIn("Acceptable use", body["body_md"])

    def test_privacy_endpoint_serves_seeded_text(self):
        resp = self.client.get("/api/policies/privacy")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Privacy Policy", resp.json()["title"])

    def test_unknown_policy_is_404(self):
        resp = self.client.get("/api/policies/not-a-policy")
        self.assertEqual(resp.status_code, 404)


class ModerationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "staffer", "staff@example.com", "Str0ng-Pass!", is_staff=True
        )
        self.target = User.objects.create_user("target", "t@example.com", "Str0ng-Pass!")
        self.active_monitor = Monitor.objects.create(
            owner=self.target, name="Active", url="https://example.com"
        )
        self.paused_monitor = Monitor.objects.create(
            owner=self.target, name="User-paused", url="https://example.org", is_active=False
        )
        self.admin_access = create_access_token(self.admin)
        self.target_access = create_access_token(self.target)

    def _post(self, path, token=None, body=None):
        return self.client.post(
            path,
            data=json.dumps(body or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.admin_access}",
        )

    def test_non_staff_cannot_disable(self):
        resp = self._post(
            f"/api/auth/moderation/users/{self.target.pk}/disable",
            token=self.target_access,
            body={"reason": "manual"},
        )
        self.assertEqual(resp.status_code, 403)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_disable_pauses_monitors_and_blocks_login(self):
        resp = self._post(
            f"/api/auth/moderation/users/{self.target.pk}/disable",
            body={"reason": "tos_violation"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])
        self.assertEqual(resp.json()["monitors_paused"], 1)

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.target.disabled_reason, "tos_violation")
        self.assertIsNotNone(self.target.disabled_at)
        self.assertEqual(self.target.paused_monitor_ids, [self.active_monitor.pk])

        self.active_monitor.refresh_from_db()
        self.assertFalse(self.active_monitor.is_active)

        audit = AuditLogEntry.objects.filter(kind="moderation.user_disabled")
        self.assertEqual(audit.count(), 1)
        self.assertEqual(audit.get().payload["reason"], "tos_violation")

        login = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "target", "password": "Str0ng-Pass!"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 401)

        # An access token minted before the ban is refused too.
        me = self.client.get(
            "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {self.target_access}"
        )
        self.assertEqual(me.status_code, 401)

    def test_enable_resumes_only_moderation_paused_monitors(self):
        self._post(f"/api/auth/moderation/users/{self.target.pk}/disable")
        resp = self._post(f"/api/auth/moderation/users/{self.target.pk}/enable")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_active"])

        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(self.target.disabled_reason, "")
        self.assertEqual(self.target.paused_monitor_ids, [])

        self.active_monitor.refresh_from_db()
        self.paused_monitor.refresh_from_db()
        self.assertTrue(self.active_monitor.is_active)
        self.assertFalse(self.paused_monitor.is_active)  # untouched
        self.assertTrue(
            AuditLogEntry.objects.filter(kind="moderation.user_enabled").exists()
        )

    def test_staff_cannot_disable_themselves(self):
        resp = self._post(f"/api/auth/moderation/users/{self.admin.pk}/disable")
        self.assertEqual(resp.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_unknown_user_is_404_and_bad_reason_is_422(self):
        resp = self._post("/api/auth/moderation/users/999999/disable")
        self.assertEqual(resp.status_code, 404)
        resp = self._post(
            f"/api/auth/moderation/users/{self.target.pk}/disable",
            body={"reason": "because"},
        )
        self.assertEqual(resp.status_code, 422)
