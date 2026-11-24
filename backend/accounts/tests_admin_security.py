"""Admin hardening: superuser-only, OTP-gated, rate-limited login."""

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from accounts.admin_site import SecureAdminSite
from accounts.models import BlockedIP, User


class SecureAdminSitePermissionTests(TestCase):
    def _request(self, user):
        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_staff_without_superuser_is_denied(self):
        staff = User.objects.create_user("staff", "staff@example.com", "Str0ng-Pass!", is_staff=True)
        staff.is_verified = lambda: True  # type: ignore[attr-defined]
        self.assertFalse(SecureAdminSite().has_permission(self._request(staff)))

    def test_superuser_requires_a_verified_otp_device(self):
        root = User.objects.create_user("root", "root@example.com", "Str0ng-Pass!", is_staff=True, is_superuser=True)
        root.is_verified = lambda: False  # type: ignore[attr-defined]
        self.assertFalse(SecureAdminSite().has_permission(self._request(root)))
        root.is_verified = lambda: True  # type: ignore[attr-defined]
        self.assertTrue(SecureAdminSite().has_permission(self._request(root)))

    def test_anonymous_is_denied(self):
        self.assertFalse(SecureAdminSite().has_permission(self._request(None)))


class AdminLoginProtectionTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        # The admin failure counter lives in the shared cache.
        cache.clear()

    def test_login_page_renders_the_otp_field(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "otp_token")

    def test_superuser_with_totp_can_log_in(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from accounts.tests_otp import _totp_code

        root = User.objects.create_user("root", "root@example.com", "Str0ng-Pass!", is_staff=True, is_superuser=True)
        device = TOTPDevice.objects.create(user=root, name="default", confirmed=True)
        response = self.client.post(
            "/admin/login/",
            {
                "username": "root",
                "password": "Str0ng-Pass!",
                "otp_token": _totp_code(device),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    @override_settings(
        ADMIN_LOGIN_DELAY_SECONDS=0,
        ADMIN_LOGIN_MAX_FAILURES=2,
        ADMIN_LOGIN_LOCK_SECONDS=300,
        ADMIN_RATE_LIMIT_PER_MIN=0,
    )
    def test_repeated_failures_block_the_ip(self):
        for _ in range(2):
            response = self.client.post("/admin/login/", {"username": "nobody", "password": "wrong-password"})
            self.assertEqual(response.status_code, 200)
        self.assertTrue(BlockedIP.objects.filter(ip="127.0.0.1").exists())
        blocked = self.client.get("/admin/")
        self.assertEqual(blocked.status_code, 403)

    @override_settings(ADMIN_ENABLED=True, ADMIN_IP_ALLOWLIST=["192.0.2.10"], ADMIN_RATE_LIMIT_PER_MIN=0)
    def test_non_allowlisted_ip_gets_404(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 404)

    @override_settings(ADMIN_ENABLED=True, ADMIN_IP_ALLOWLIST=["*"], ADMIN_RATE_LIMIT_PER_MIN=0)
    def test_wildcard_allowlist_reaches_the_login_page(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)

    def test_permissions_policy_header_is_present(self):
        response = self.client.get("/api/health")
        self.assertIn("camera=()", response["Permissions-Policy"])
