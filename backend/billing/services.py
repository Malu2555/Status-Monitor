"""Stripe client wrappers, plan definitions and webhook→DB synchronization."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:  # import-time only (avoids a circular import with accounts)
    from .models import Subscription

logger = logging.getLogger("billing")

PLANS = {
    "free": {
        "label": "Free",
        "monitors": 1,
        "min_interval": 300,
        "price_id": settings.STRIPE_PRICE_IDS.get("free", ""),
    },
    "pro": {
        "label": "Pro",
        "monitors": 10,
        "min_interval": 60,
        "price_id": settings.STRIPE_PRICE_IDS.get("pro", ""),
    },
    "business": {
        "label": "Business",
        "monitors": 50,
        "min_interval": 60,
        "price_id": settings.STRIPE_PRICE_IDS.get("business", ""),
    },
}

ACTIVE_STATUSES = ("active", "trialing")


class StripeNotConfigured(RuntimeError):
    pass


def _active_subscription(user) -> Subscription | None:
    subscription = getattr(user, "subscription", None)
    if subscription is not None and subscription.status in ACTIVE_STATUSES:
        return subscription
    return None


def get_plan_name(user) -> str:
    subscription = _active_subscription(user)
    return subscription.plan if subscription else "free"


def monitors_limit(user) -> int:
    return PLANS[get_plan_name(user)]["monitors"]


def min_interval(user) -> int:
    return PLANS[get_plan_name(user)]["min_interval"]


def can_add_monitor(user) -> tuple[bool, str]:
    count = user.monitors.count()
    limit = monitors_limit(user)
    if count >= limit:
        return False, f"Plan limit reached ({count}/{limit} monitors). Upgrade to add more."
    return True, ""


def get_plan_summary(user) -> dict:
    subscription = _active_subscription(user)
    plan = get_plan_name(user)
    return {
        "plan": plan,
        "label": PLANS[plan]["label"],
        "monitors_used": user.monitors.count(),
        "monitors_limit": monitors_limit(user),
        "subscription_status": subscription.status if subscription else "active",
    }


def stripe_api():
    if not settings.STRIPE_SECRET_KEY:
        raise StripeNotConfigured("Stripe is not configured on this server.")
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _frontend_url(path: str = "") -> str:
    origin = getattr(settings, "FRONTEND_URL", None) or "http://localhost:5173"
    return origin + path


def create_checkout_session(user, plan: str) -> str:
    if plan not in ("pro", "business"):
        raise ValueError("Unknown plan.")
    stripe = stripe_api()
    price_id = PLANS[plan]["price_id"]
    if not price_id:
        raise ValueError("Stripe price for this plan is not configured.")
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.pk)})
        user.stripe_customer_id = customer["id"]
        user.save(update_fields=["stripe_customer_id"])
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=user.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"user_id": str(user.pk), "plan": plan},
        success_url=_frontend_url("/dashboard?billing=success"),
        cancel_url=_frontend_url("/dashboard?billing=cancel"),
    )
    return session["url"]


def create_portal_session(user) -> str:
    if not user.stripe_customer_id:
        raise ValueError("No Stripe customer exists yet — subscribe first.")
    stripe = stripe_api()
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id, return_url=_frontend_url("/dashboard")
    )
    return session["url"]


def _plan_for_price(price_id: str):
    for plan, config in PLANS.items():
        if config["price_id"] == price_id:
            return plan
    return None


def _ts_to_dt(timestamp):
    if not timestamp:
        return None
    return datetime.fromtimestamp(int(timestamp), tz=UTC)


def handle_webhook_event(event: dict) -> None:
    """Sync a verified Stripe event into Subscription rows."""
    from .models import Subscription

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        from accounts.models import User

        user = User.objects.filter(pk=data.get("metadata", {}).get("user_id", "")).first()
        sub_id = data.get("subscription")
        plan = data.get("metadata", {}).get("plan", "pro")
        customer = data.get("customer", "")
        if user is None or not sub_id:
            return
        if customer:
            user.stripe_customer_id = customer
            user.save(update_fields=["stripe_customer_id"])
        logger.info(
            "webhook checkout.session.completed: user=%s sub=%s plan=%s", user.pk, sub_id, plan
        )
        Subscription.objects.update_or_create(
            user=user,
            defaults={
                "plan": plan if plan in PLANS else "pro",
                "status": "active",
                "stripe_subscription_id": sub_id,
                "stripe_customer_id": customer,
                "current_period_end": _ts_to_dt(data.get("current_period_end")),
            },
        )
        return

    if event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        subscription = Subscription.objects.filter(stripe_subscription_id=data.get("id")).first()
        if subscription is None:
            return
        status = data.get("status", "canceled")
        if status in ("canceled", "unpaid", "incomplete_expired"):
            subscription.status = Subscription.Status.CANCELED
            subscription.plan = "free"
        else:
            plan = None
            items = data.get("items", {}).get("data", []) if isinstance(data.get("items"), dict) else []
            for item in items:
                plan = _plan_for_price((item.get("price") or {}).get("id", ""))
                if plan:
                    break
            subscription.status = status
            if plan:
                subscription.plan = plan
        subscription.current_period_end = _ts_to_dt(data.get("current_period_end"))
        logger.info(
            "webhook %s: sub=%s user=%s status=%s",
            event_type,
            data.get("id"),
            subscription.user.pk,
            subscription.status,
        )
        subscription.save()
        return

