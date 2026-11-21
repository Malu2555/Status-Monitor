"""Self-service account management: password, email, sessions, deletion."""
import json

from django.core import mail
from django.test import TestCase

from accounts.models import AccountActionToken, User
from accounts.services import create_access_token
from monitors.models import Monitor


class _Base(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("self1", "self1@example.com", "Old-Passw0rd!")
        self.access = create_access_token(self.user)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.access}"}

    def _post(self, path, body=None):
        return self.client.post(
            path, data=json.dumps(body or {}), content_type="application/json", **self.auth
        )


class PasswordChangeTests(_Base):
    def test_rotates_password_and_returns_fresh_tokens(self):
        resp = self._post(
            "/api/auth/change-password",
            {"current_password": "Old-Passw0rd!", "new_password": "New-Passw0rd!"},
        )
        self.assertEqual(resp.status_code, 200)
        new_access = resp.json()["access"]
        self.assertNotEqual(new_access, self.access)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.tokens_invalid_before)

        # The pre-change token is dead, the replacement works.
        self.assertEqual(self.client.get("/api/auth/me", **self.auth).status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {new_access}"
            ).status_code,
            200,
        )
        login = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": "self1", "password": "New-Passw0rd!"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)

    def test_wrong_current_password_is_rejected(self):
        resp = self._post(
            "/api/auth/change-password",
            {"current_password": "nope", "new_password": "New-Passw0rd!"},
        )
        self.assertEqual(resp.status_code, 400)


class EmailChangeTests(_Base):
    def test_confirmation_link_switches_the_email(self):
        resp = self._post(
            "/api/auth/change-email",
            {"new_email": "new@example.com", "current_password": "Old-Passw0rd!"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])

        # Old address still active until the link is followed.
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "self1@example.com")

        token = AccountActionToken.objects.get(purpose="email_change")
        verify = self.client.post(
            "/api/auth/verify-email",
            data=json.dumps({"token": token.id}),
            content_type="application/json",
        )
        self.assertEqual(verify.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertTrue(self.user.email_verified)

    def test_duplicate_email_rejected(self):
        User.objects.create_user("other", "taken@example.com", "Str0ng-Pass!")
        resp = self._post(
            "/api/auth/change-email",
            {"new_email": "taken@example.com", "current_password": "Old-Passw0rd!"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_wrong_password_rejected(self):
        resp = self._post(
            "/api/auth/change-email",
            {"new_email": "new@example.com", "current_password": "nope"},
        )
        self.assertEqual(resp.status_code, 400)


class SessionRevokeTests(_Base):
    def test_other_sessions_are_invalidated(self):
        resp = self._post("/api/auth/sessions/revoke-others")
        self.assertEqual(resp.status_code, 200)
        new_access = resp.json()["access"]

        self.assertEqual(self.client.get("/api/auth/me", **self.auth).status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {new_access}"
            ).status_code,
            200,
        )


class DeleteAccountTests(_Base):
    def test_delete_anonymises_disables_and_pauses_monitors(self):
        monitor = Monitor.objects.create(
            owner=self.user, name="Mine", url="https://example.com"
        )
        resp = self.client.delete(
            "/api/auth/me",
            data=json.dumps({"current_password": "Old-Passw0rd!"}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(resp.status_code, 204)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.username, f"deleted-{self.user.pk}")
        self.assertTrue(self.user.email.endswith("@deleted.invalid"))
        self.assertEqual(self.user.disabled_reason, "self_deleted")
        self.assertFalse(self.user.has_usable_password())

        monitor.refresh_from_db()
        self.assertFalse(monitor.is_active)

        login = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": f"deleted-{self.user.pk}", "password": "Old-Passw0rd!"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 401)

    def test_delete_requires_the_password(self):
        resp = self.client.delete(
            "/api/auth/me",
            data=json.dumps({"current_password": "wrong"}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(resp.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
