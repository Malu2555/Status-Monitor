"""Owner-scoped notification channel API (list/create/update/delete/test)."""
import json
from unittest import mock

from django.core import mail
from django.test import TestCase

from accounts.models import User
from accounts.services import create_access_token
from monitors.models import Monitor
from notifications.models import MonitorNotificationChannel


class NotificationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("chan", "chan@example.com", "Str0ng-Pass!")
        self.other = User.objects.create_user("peer", "peer@example.com", "Str0ng-Pass!")
        self.monitor = Monitor.objects.create(
            owner=self.user, name="Site", url="https://example.com"
        )
        self.access = create_access_token(self.user)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.access}"}

    def _create(self, kind="email", address=None, monitor_id=None):
        return self.client.post(
            "/api/notifications/channels",
            data=json.dumps(
                {
                    "monitor_id": monitor_id or self.monitor.pk,
                    "kind": kind,
                    "address": address or self.user.email,
                }
            ),
            content_type="application/json",
            **self.auth,
        )

    def test_create_list_patch_delete(self):
        created = self._create()
        self.assertEqual(created.status_code, 201)
        channel_id = created.json()["id"]
        self.assertEqual(created.json()["monitor_name"], "Site")

        listed = self.client.get("/api/notifications/channels", **self.auth)
        self.assertEqual(len(listed.json()), 1)

        patched = self.client.patch(
            f"/api/notifications/channels/{channel_id}",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(patched.json()["enabled"])

        deleted = self.client.delete(
            f"/api/notifications/channels/{channel_id}", **self.auth
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(MonitorNotificationChannel.objects.exists())

    def test_duplicate_channel_is_rejected(self):
        self.assertEqual(self._create().status_code, 201)
        self.assertEqual(self._create().status_code, 400)

    def test_webhook_address_must_be_a_url(self):
        resp = self._create(kind="slack", address="not-a-url")
        self.assertEqual(resp.status_code, 422)

    def test_telegram_address_shape_is_enforced(self):
        self.assertEqual(self._create(kind="telegram", address="1234").status_code, 422)
        self.assertEqual(
            self._create(kind="telegram", address="1234|5678").status_code, 201
        )

    def test_test_endpoint_sends_an_email(self):
        channel_id = self._create().json()["id"]
        resp = self.client.post(
            f"/api/notifications/channels/{channel_id}/test", **self.auth
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["detail"], "Test message delivered.")
        self.assertEqual(len(mail.outbox), 1)

    def test_test_endpoint_reports_provider_errors(self):
        channel_id = self._create().json()["id"]
        with mock.patch(
            "notifications.channels.send_mail", side_effect=RuntimeError("smtp down")
        ):
            resp = self.client.post(
                f"/api/notifications/channels/{channel_id}/test", **self.auth
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["detail"], "Test message failed.")
        self.assertIn("RuntimeError", resp.json()["last_error"])

    def test_cannot_touch_another_users_channel(self):
        foreign = MonitorNotificationChannel.objects.create(
            user=self.other,
            monitor=Monitor.objects.create(
                owner=self.other, name="Theirs", url="https://example.org"
            ),
            kind="email",
            address="theirs@example.com",
        )
        patched = self.client.patch(
            f"/api/notifications/channels/{foreign.pk}",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(patched.status_code, 404)
        self.assertEqual(
            self.client.delete(
                f"/api/notifications/channels/{foreign.pk}", **self.auth
            ).status_code,
            404,
        )
        self.assertTrue(MonitorNotificationChannel.objects.filter(pk=foreign.pk).exists())

    def test_cannot_attach_a_channel_to_a_foreign_monitor(self):
        resp = self._create(monitor_id=self.monitor.pk + 999)
        self.assertEqual(resp.status_code, 404)
