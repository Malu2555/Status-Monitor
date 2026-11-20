"""2FA recovery codes: issuance, login, consumption, regeneration, cleanup."""
import json

from django.test import TestCase

from accounts.models import RecoveryCode, User
from accounts.services import create_access_token, verify_otp_or_recovery


def _totp_code(device) -> str:
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


class RecoveryCodeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("dave", "dave@example.com", "Str0ng-Pass!")
        self.access = create_access_token(self.user)

    def _post(self, url, payload=None):
        return self.client.post(
            url,
            json.dumps(payload or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

    def _enable(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self._post("/api/auth/otp/enroll")
        device = TOTPDevice.objects.get(user=self.user)
        resp = self._post("/api/auth/otp/activate", {"code": _totp_code(device)})
        self.assertEqual(resp.status_code, 200, resp.content)
        return device, resp.json()["recovery_codes"]

    def _login(self, otp=None):
        payload = {"username": "dave", "password": "Str0ng-Pass!"}
        if otp is not None:
            payload["otp"] = otp
        return self.client.post(
            "/api/auth/login", json.dumps(payload), content_type="application/json"
        )

    def test_activation_returns_ten_codes(self):
        _, codes = self._enable()
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertEqual(RecoveryCode.objects.filter(user=self.user).count(), 10)

    def test_summary_counts_unused(self):
        _, codes = self._enable()
        resp = self.client.get(
            "/api/auth/otp/recovery-codes", HTTP_AUTHORIZATION=f"Bearer {self.access}"
        )
        self.assertEqual(resp.json(), {"total": 10, "unused": 10})
        self.assertTrue(verify_otp_or_recovery(self.user, codes[0]))
        resp = self.client.get(
            "/api/auth/otp/recovery-codes", HTTP_AUTHORIZATION=f"Bearer {self.access}"
        )
        self.assertEqual(resp.json()["unused"], 9)

    def test_recovery_code_logs_in_once(self):
        _, codes = self._enable()
        self.assertEqual(self._login(codes[0]).status_code, 200)
        self.assertEqual(self._login(codes[0]).status_code, 401)

    def test_recovery_code_accepts_lowercase_without_dashes(self):
        _, codes = self._enable()
        loose = codes[1].replace("-", "").lower()
        self.assertTrue(verify_otp_or_recovery(self.user, loose))

    def test_regenerate_invalidates_old_codes(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device, old_codes = self._enable()
        TOTPDevice.objects.filter(pk=device.pk).update(last_t=1)
        resp = self._post(
            "/api/auth/otp/recovery-codes/regenerate", {"code": _totp_code(device)}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        new_codes = resp.json()["recovery_codes"]
        self.assertEqual(len(new_codes), 10)
        self.assertFalse(verify_otp_or_recovery(self.user, old_codes[0]))
        self.assertTrue(verify_otp_or_recovery(self.user, new_codes[0]))

    def test_disable_removes_recovery_codes(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device, _ = self._enable()
        TOTPDevice.objects.filter(pk=device.pk).update(last_t=1)
        resp = self._post("/api/auth/otp/disable", {"code": _totp_code(device)})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(RecoveryCode.objects.filter(user=self.user).count(), 0)
