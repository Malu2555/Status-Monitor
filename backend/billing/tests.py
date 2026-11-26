import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import User
from accounts.services import create_access_token
from billing.models import Subscription, WebhookEvent
from billing.services import (
    PLANS,
    can_add_monitor,
    get_plan_summary,
    handle_webhook_event,
    monitors_limit,
)
from monitors.models import Monitor

SECRET = "whsec_" + base64.b64encode(b"test-webhook-secret").decode()
SECRET_KEY_BYTES = base64.b64decode(SECRET[6:])


def polar_event(
    event_type="subscription.created",
    *,
    sub_id="sub_1",
    product_id="",
    status="active",
    customer_id="cus_1",
    metadata=None,
    period_end="2030-01-01T00:00:00Z",
):
    return {
        "type": event_type,
        "data": {
            "id": sub_id,
            "status": status,
            "product_id": product_id,
            "customer_id": customer_id,
            "current_period_end": period_end,
            "customer": {"id": customer_id, "email": "hook@example.com"},
            "metadata": metadata or {},
        },
    }


class BillingLogicTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", "t@example.com", "password123")

    def test_free_defaults(self):
        self.assertEqual(monitors_limit(self.user), 1)
        ok, _ = can_add_monitor(self.user)
        self.assertTrue(ok)
        summary = get_plan_summary(self.user)
        self.assertEqual(summary["plan"], "free")
        self.assertEqual(summary["monitors_used"], 0)

    def test_pro_plan_raises_limit(self):
        Subscription.objects.create(user=self.user, plan="pro", status="active")
        self.assertEqual(monitors_limit(self.user), 10)
        self.assertEqual(get_plan_summary(self.user)["plan"], "pro")

    def test_canceled_without_period_falls_back_to_free(self):
        Subscription.objects.create(user=self.user, plan="pro", status="canceled")
        self.assertEqual(monitors_limit(self.user), 1)

    def test_plan_limit_enforcement(self):
        Subscription.objects.create(user=self.user, plan="pro", status="active")
        for index in range(10):
            Monitor.objects.create(owner=self.user, name=f"M{index}", url=f"https://example{index}.com")
        ok, reason = can_add_monitor(self.user)
        self.assertFalse(ok)
        self.assertIn("limit", reason.lower())


class WebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hookuser", "hook@example.com", "password123")

    def _event(self, plan="pro"):
        return polar_event(metadata={"user_id": str(self.user.pk), "plan": plan})

    def test_duplicate_delivery_processed_once(self):
        handle_webhook_event(self._event("pro"), "delivery-1")
        # A replay may carry different data; it must be ignored.
        handle_webhook_event(self._event("business"), "delivery-1")
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.plan, "pro")
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertIsNotNone(WebhookEvent.objects.get(id="delivery-1").processed_at)

    def test_distinct_deliveries_both_processed(self):
        handle_webhook_event(self._event("pro"), "d1")
        handle_webhook_event(self._event("business"), "d2")
        self.assertEqual(Subscription.objects.get(user=self.user).plan, "business")
        self.assertEqual(WebhookEvent.objects.count(), 2)

    def test_event_without_delivery_still_applied(self):
        handle_webhook_event(self._event(), "")
        self.assertTrue(Subscription.objects.filter(user=self.user).exists())

    def test_subscription_revoked_drops_to_free(self):
        Subscription.objects.create(user=self.user, plan="pro", status="active", polar_subscription_id="sub_99")
        handle_webhook_event({"type": "subscription.revoked", "data": {"id": "sub_99"}}, "revoke-1")
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.status, Subscription.Status.CANCELED)
        self.assertEqual(subscription.plan, "free")

    def test_subscription_canceled_keeps_plan_until_period_end(self):
        subscription = Subscription.objects.create(
            user=self.user, plan="pro", status="active", polar_subscription_id="sub_77"
        )
        handle_webhook_event(
            {
                "type": "subscription.canceled",
                "data": {"id": "sub_77", "current_period_end": "2030-01-01T00:00:00Z"},
            },
            "cancel-1",
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.CANCELED)
        self.assertEqual(subscription.plan, "pro")  # still paid through the period
        self.assertEqual(monitors_limit(self.user), 10)

    def test_webhook_processed_audit_once(self):
        from audit.models import AuditLogEntry

        handle_webhook_event(self._event(), "delivery-audit")
        handle_webhook_event(self._event("business"), "delivery-audit")
        self.assertEqual(
            AuditLogEntry.objects.filter(kind="billing.webhook_processed", payload__event_id="delivery-audit").count(),
            1,
        )


@override_settings(POLAR_WEBHOOK_SECRET=SECRET)
class WebhookSignatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("siguser", "sig@example.com", "password123")
        self.body = json.dumps(polar_event(metadata={"user_id": str(self.user.pk), "plan": "pro"})).encode()
        self.timestamp = str(int(time.time()))

    def _headers(self, body, msg_id="msg-1", timestamp=None):
        ts = timestamp or self.timestamp
        signed = f"{msg_id}.{ts}.".encode() + body
        signature = base64.b64encode(hmac.new(SECRET_KEY_BYTES, signed, hashlib.sha256).digest()).decode()
        return {
            "Webhook-Id": msg_id,
            "Webhook-Timestamp": ts,
            "Webhook-Signature": f"v1,{signature}",
        }

    def test_valid_signature_processes(self):
        response = self.client.post(
            "/api/billing/webhook",
            self.body,
            content_type="application/json",
            headers=self._headers(self.body),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subscription.objects.get(user=self.user).plan, "pro")

    def test_tampered_body_rejected(self):
        response = self.client.post(
            "/api/billing/webhook",
            self.body + b" ",
            content_type="application/json",
            headers=self._headers(self.body),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Subscription.objects.filter(user=self.user).exists())

    def test_stale_timestamp_rejected(self):
        headers = self._headers(self.body, timestamp=str(int(time.time()) - 3600))
        response = self.client.post(
            "/api/billing/webhook",
            self.body,
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)


class CheckoutGuardTests(TestCase):
    """Checkout fails closed until Polar is configured for the plan.

    `PLANS` snapshots `POLAR_PRODUCT_IDS` at import time, so the plan-level guard
    is exercised by patching the table entry instead of `override_settings`.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            "buyer", "buyer@example.com", "password123", email_verified=True
        )
        self.access = create_access_token(self.user)

    def _checkout(self, plan="pro"):
        return self.client.post(
            "/api/billing/checkout",
            json.dumps({"plan": plan}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.access}",
        )

    def test_checkout_rejected_while_polar_product_is_unconfigured(self):
        # This is the "Coming soon" contract: no product id -> no purchase.
        with patch.dict(PLANS["pro"], {"product_id": ""}):
            response = self._checkout("pro")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not configured", response.json()["detail"].lower())

    def test_checkout_never_calls_polar_without_a_product_id(self):
        with patch.dict(PLANS["business"], {"product_id": ""}):
            with patch("billing.services.httpx.post") as post:
                response = self._checkout("business")
        self.assertEqual(response.status_code, 400)
        post.assert_not_called()

    @override_settings(POLAR_ACCESS_TOKEN="")
    def test_checkout_reports_unconfigured_polar(self):
        with patch.dict(PLANS["pro"], {"product_id": "prod_test"}):
            response = self._checkout("pro")
        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"].lower())
