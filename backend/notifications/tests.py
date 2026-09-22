from unittest import mock

from django.core import mail
from django.test import TestCase

from accounts.models import User
from monitors.models import Monitor
from notifications.models import MonitorNotificationChannel, NotificationDelivery
from notifications.services import deliver_pending, enqueue_state_transition


class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notifuser", "n@example.com", "password123")
        self.monitor = Monitor.objects.create(
            owner=self.user,
            name="Site",
            url="https://example.com",
            last_status=Monitor.Status.UP,
        )

    def _channel(self, kind="email", address="ops@example.com"):
        return MonitorNotificationChannel.objects.create(
            user=self.user, monitor=self.monitor, kind=kind, address=address
        )

    def test_transition_enqueues_per_channel(self):
        self._channel()
        self._channel(address="team@example.com")
        count = enqueue_state_transition(
            self.monitor,
            Monitor.Status.UP,
            Monitor.Status.DOWN,
            {"status_code": None, "response_ms": 1000, "error": "timeout"},
        )
        self.assertEqual(count, 2)
        rows = NotificationDelivery.objects.filter(monitor=self.monitor)
        self.assertEqual(rows.count(), 2)
        self.assertTrue(all(row.event_kind == "down" for row in rows))

    def test_first_check_success_is_silent(self):
        self._channel()
        count = enqueue_state_transition(self.monitor, Monitor.Status.UNKNOWN, Monitor.Status.UP, {})
        self.assertEqual(count, 0)
        self.assertEqual(NotificationDelivery.objects.count(), 0)

    def test_no_transition_no_delivery(self):
        self._channel()
        count = enqueue_state_transition(self.monitor, Monitor.Status.UP, Monitor.Status.UP, {})
        self.assertEqual(count, 0)

    def test_email_delivery_success(self):
        self._channel()
        enqueue_state_transition(
            self.monitor,
            Monitor.Status.UP,
            Monitor.Status.DOWN,
            {"status_code": 500, "response_ms": 12, "error": ""},
        )
        sent, failed, dead = deliver_pending()
        self.assertEqual((sent, failed, dead), (1, 0, 0))
        row = NotificationDelivery.objects.get()
        self.assertEqual(row.status, NotificationDelivery.Status.SENT)
        self.assertIsNotNone(row.sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_failed_delivery_retries_then_dies(self):
        self._channel()
        enqueue_state_transition(self.monitor, Monitor.Status.UP, Monitor.Status.DOWN, {})
        with mock.patch("notifications.channels.send_mail", side_effect=RuntimeError("smtp down")):
            for _ in range(8):
                deliver_pending(max_attempts=8)
        row = NotificationDelivery.objects.get()
        self.assertEqual(row.status, NotificationDelivery.Status.DEAD)
        self.assertEqual(row.attempts, 8)
        self.assertIn("RuntimeError", row.last_error)

    def test_webhook_delivery_success(self):
        self._channel(kind="webhook", address="https://hooks.example.com/x")
        enqueue_state_transition(self.monitor, Monitor.Status.UP, Monitor.Status.DOWN, {})
        with mock.patch("notifications.channels.httpx.Client"):
            sent, failed, dead = deliver_pending()
        self.assertEqual((sent, failed, dead), (1, 0, 0))
        row = NotificationDelivery.objects.get()
        self.assertEqual(row.status, NotificationDelivery.Status.SENT)
