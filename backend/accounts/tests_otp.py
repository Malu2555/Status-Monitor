"""Opt-in TOTP two-factor flows: enroll → activate → login gate → disable."""

import json

from django.test import TestCase, override_settings

from accounts.models import User
from accounts.services import create_access_token


def _totp_code(device) -> str:
    """Compute the current TOTP code for a device (test helper)."""
    from django_otp.oath import TOTP

    return str(
        TOTP(
            device.bin_key,
            step=device.step,
            t0=device.t0,
            digits=device.digits,
            drift=device.drift,
        ).token()
    )


@override_settings(OTP_TOTP_THROTTLE_FACTOR=0)
class OtpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("carol", "c@example.com", "Str0ng-Pass!")
        self.access = create_access_token(self.user)

    def _authed_post(self, url, payload=None):
        return self.client.post(
            url,
            json.dumps(payload or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

    def _login(self, otp=None):
        payload = {"username": "carol", "password": "Str0ng-Pass!"}
        if otp is not None:
            payload["otp"] = otp
        return self.client.post("/api/auth/login", json.dumps(payload), content_type="application/json")

    def test_enroll_then_activate_then_login_gate(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        response = self._authed_post("/api/auth/otp/enroll")
        self.assertEqual(response.status_code, 200)
        self.assertIn("otpauth://", response.json()["provisioning_uri"])
        device = TOTPDevice.objects.get(user=self.user)
        self.assertFalse(device.confirmed)

        # Wrong code refused.
        self.assertEqual(self._authed_post("/api/auth/otp/activate", {"code": "000000"}).status_code, 400)
        # django-otp's verification throttle is disabled in tests
        # (settings.OTP_TOTP_THROTTLE_FACTOR = 0), so no sleep is needed.

        # Valid code activates the device.
        response = self._authed_post("/api/auth/otp/activate", {"code": _totp_code(device)})
        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)

        # Skip django-otp's replay guard so a same-step code can verify twice.
        TOTPDevice.objects.filter(pk=device.pk).update(last_t=1)

        # Login now demands a valid TOTP code.
        self.assertEqual(self._login().status_code, 401)
        self.assertEqual(self._login(otp="000000").status_code, 401)
        self.assertEqual(self._login(otp=_totp_code(device)).status_code, 200)

    def test_otp_status_and_disable_flow(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        response = self.client.get("/api/auth/otp/status", HTTP_AUTHORIZATION=f"Bearer {self.access}")
        self.assertEqual(response.json()["enabled"], False)

        self._authed_post("/api/auth/otp/enroll")
        device = TOTPDevice.objects.get(user=self.user)
        self._authed_post("/api/auth/otp/activate", {"code": _totp_code(device)})
        TOTPDevice.objects.filter(pk=device.pk).update(last_t=1)

        response = self.client.get("/api/auth/otp/status", HTTP_AUTHORIZATION=f"Bearer {self.access}")
        self.assertEqual(response.json()["enabled"], True)

        response = self._authed_post("/api/auth/otp/disable", {"code": _totp_code(device)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        # 2FA no longer required.
        self.assertEqual(self._login().status_code, 200)
