from typing import Any, cast

from django.test import TestCase

from accounts.models import User
from billing.models import StripeEvent, Subscription
from billing.services import (
    can_add_monitor,
    get_plan_summary,
    handle_webhook_event,
    monitors_limit,
)


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

    def test_canceled_subscription_falls_back_to_free(self):
        Subscription.objects.create(
            user=self.user, plan="pro", status="canceled", stripe_subscription_id="sub_123"
        )
        self.assertEqual(monitors_limit(self.user), 1)

    def test_plan_limit_enforcement(self):
        Subscription.objects.create(user=self.user, plan="pro", status="active")
        for index in range(10):
            cast(Any, self.user).monitors.create(
                name=f"M{index}", url=f"https://example{index}.com"
            )
        ok, reason = can_add_monitor(self.user)
        self.assertFalse(ok)
        self.assertIn("limit", reason.lower())


class WebhookIdempotencyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hookuser", "hook@example.com", "password123")

    def _checkout_event(self, event_id="evt_dup", plan="pro"):
        return {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "subscription": "sub_123",
                    "metadata": {"user_id": str(self.user.pk), "plan": plan},
                    "current_period_end": 2000000000,
                }
            },
        }

    def test_duplicate_delivery_processed_once(self):
        handle_webhook_event(self._checkout_event())
        # A Stripe replay may carry a different payload; it must be ignored.
        handle_webhook_event(self._checkout_event(plan="business"))
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.plan, "pro")
        self.assertEqual(StripeEvent.objects.count(), 1)
        self.assertIsNotNone(StripeEvent.objects.get(id="evt_dup").processed_at)

    def test_distinct_events_both_processed(self):
        handle_webhook_event(self._checkout_event(event_id="evt_1", plan="pro"))
        handle_webhook_event(self._checkout_event(event_id="evt_2", plan="business"))
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.plan, "business")
        self.assertEqual(StripeEvent.objects.count(), 2)

    def test_event_without_id_still_applied(self):
        handle_webhook_event(self._checkout_event(event_id=""))
        self.assertTrue(Subscription.objects.filter(user=self.user).exists())

    def test_subscription_updated_applied(self):
        Subscription.objects.create(
            user=self.user,
            plan="pro",
            status="active",
            stripe_subscription_id="sub_99",
        )
        handle_webhook_event(
            {
                "id": "evt_upd",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": "sub_99", "status": "canceled"}},
            }
        )
        subscription = Subscription.objects.get(user=self.user)
        self.assertEqual(subscription.status, Subscription.Status.CANCELED)
        self.assertEqual(subscription.plan, "free")

    def test_webhook_processed_audit_once(self):
        handle_webhook_event(self._checkout_event())
        handle_webhook_event(self._checkout_event(plan="business"))
        from audit.models import AuditLogEntry

        self.assertEqual(
            AuditLogEntry.objects.filter(
                kind="billing.webhook_processed", payload__event_id="evt_dup"
            ).count(),
            1,
        )
