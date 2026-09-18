from django.test import TestCase
from typing import Any, cast

from accounts.models import User
from billing.models import Subscription
from billing.services import can_add_monitor, get_plan_summary, monitors_limit


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
