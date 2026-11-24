import json
from unittest import mock

from django.test import TestCase

from accounts.models import User
from audit.models import AuditLogEntry
from audit.services import audit_log


class AuditServiceTests(TestCase):
    def test_audit_log_creates_row_with_user(self):
        user = User.objects.create_user("audituser", "a@example.com", "password123")
        row = audit_log(None, "auth.login", user=user, username=user.username)
        self.assertIsNotNone(row)
        entry = AuditLogEntry.objects.get()
        self.assertEqual(entry.kind, "auth.login")
        self.assertEqual(entry.user, user)
        self.assertEqual(entry.payload["username"], "audituser")

    def test_audit_log_never_breaks_callers(self):
        with mock.patch(
            "audit.services.AuditLogEntry.objects.create",
            side_effect=RuntimeError("db down"),
        ):
            with self.assertLogs("audit", level="ERROR"):
                row = audit_log(None, "auth.login", user=None)
        self.assertIsNone(row)


class AuditHookTests(TestCase):
    def test_register_writes_audit_row(self):
        response = self.client.post(
            "/api/auth/register",
            json.dumps(
                {
                    "username": "newuser",
                    "email": "new@example.com",
                    "password": "Str0ng-Pass!",
                    "accepted_tos": True,
                    "accepted_age": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditLogEntry.objects.filter(kind="auth.register", payload__username="newuser").exists())

    def test_failed_login_writes_audit_row(self):
        User.objects.create_user("knownuser", "k@example.com", "Str0ng-Pass!")
        response = self.client.post(
            "/api/auth/login",
            json.dumps({"username": "knownuser", "password": "not-the-password"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        entry = AuditLogEntry.objects.filter(kind="auth.login_failed").get()
        self.assertEqual(entry.payload["username"], "knownuser")

    def test_monitor_create_writes_audit_row(self):
        from accounts.services import create_access_token

        user = User.objects.create_user("monowner", "m@example.com", "Str0ng-Pass!")
        access = create_access_token(user)
        with mock.patch("monitors.api.validate_target_url", return_value="https://example.com"):
            response = self.client.post(
                "/api/monitors",
                json.dumps(
                    {
                        "name": "Site",
                        "url": "https://example.com",
                        "is_public": True,
                        "check_interval_seconds": 300,
                    }
                ),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {access}",
            )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditLogEntry.objects.filter(kind="monitor.create", payload__name="Site").exists())
