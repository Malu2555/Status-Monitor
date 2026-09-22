"""Account lifecycle flows: email verification + password reset."""
import json

from django.core import mail
from django.test import TestCase

from accounts.models import AccountActionToken, User
from accounts.services import create_access_token


class VerificationTests(TestCase):
    def _register(self, **overrides):
        payload = {
            "username": "alice",
            "email": "alice@example.com",
            "password": "Str0ng-Pass!",
            **overrides,
        }
        return self.client.post(
            "/api/auth/register", json.dumps(payload), content_type="application/json"
        )

    def test_register_sends_verification_email(self):
        response = self._register()
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["user"]["email_verified"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/verify-email?token=", mail.outbox[0].body)

    def test_verify_email_flow_and_single_use(self):
        self._register()
        token = AccountActionToken.objects.get()
        response = self.client.post(
            "/api/auth/verify-email",
            json.dumps({"token": token.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.get(username="alice").email_verified)
        # Tokens are single-use.
        response = self.client.post(
            "/api/auth/verify-email",
            json.dumps({"token": token.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_verify_email_bad_token(self):
        response = self.client.post(
            "/api/auth/verify-email",
            json.dumps({"token": "not-a-real-token"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_checkout_requires_verified_email(self):
        self._register()
        user = User.objects.get(username="alice")
        access = create_access_token(user)
        response = self.client.post(
            "/api/billing/checkout",
            json.dumps({"plan": "pro"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 403)

    def test_resend_verification(self):
        self._register()
        mail.outbox.clear()
        user = User.objects.get(username="alice")
        access = create_access_token(user)
        response = self.client.post(
            "/api/auth/resend-verification",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bob", "bob@example.com", "Old-Passw0rd")

    def test_request_reset_same_response_for_known_and_unknown(self):
        self.client.post(
            "/api/auth/request-reset",
            json.dumps({"email": "bob@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post(
            "/api/auth/request-reset",
            json.dumps({"email": "ghost@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)  # no new email, same response shape

    def test_reset_confirm_changes_password_and_is_single_use(self):
        self.client.post(
            "/api/auth/request-reset",
            json.dumps({"email": "bob@example.com"}),
            content_type="application/json",
        )
        token = AccountActionToken.objects.get()
        response = self.client.post(
            "/api/auth/reset-confirm",
            json.dumps({"token": token.id, "new_password": "New-Passw0rd!"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        login = self.client.post(
            "/api/auth/login",
            json.dumps({"username": "bob", "password": "New-Passw0rd!"}),
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        # Single use: the same token can't reset again.
        response = self.client.post(
            "/api/auth/reset-confirm",
            json.dumps({"token": token.id, "new_password": "Another-Pass!"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
