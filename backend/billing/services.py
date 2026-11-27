"""Polar.sh client wrappers, plan definitions and webhook→DB sync.

Polar is our merchant of record: it collects payments, handles global tax/VAT
and pays us net. We only need two REST calls (via ``httpx``, no SDK):
create a Checkout Session URL, and create a Customer Session for the portal.
Webhooks are verified with the Standard Webhooks HMAC scheme.
Everything plan-limit related is pure Django and provider independent.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from django.conf import settings
from django.utils import timezone

from audit.services import audit_log

if TYPE_CHECKING:  # import-time only (avoids a circular import with accounts)
    from .models import Subscription

logger = logging.getLogger("billing")

PLANS = {
    "free": {
        "label": "Free",
        "monitors": 1,
        "min_interval": 300,
        "status_pages": 1,
        "channels": 2,
        "product_id": "",
    },
    "pro": {
        "label": "Pro",
        "monitors": 10,
        "min_interval": 60,
        "status_pages": 3,
        "channels": 10,
        "product_id": settings.POLAR_PRODUCT_IDS.get("pro", ""),
    },
    "business": {
        "label": "Business",
        "monitors": 50,
        "min_interval": 60,
        "status_pages": None,  # unlimited
        "channels": None,  # unlimited
        "product_id": settings.POLAR_PRODUCT_IDS.get("business", ""),
    },
}

# Healthy statuses keep the plan usable unconditionally.
ACTIVE_STATUSES = ("active", "trialing")
# During dunning/cancellation Polar keeps the subscription alive until the paid
# period ends — we mirror that so customers don't lose access early.
GRACE_STATUSES = ("past_due", "canceled")

# Polar subscription status → our Subscription.Status.
_STATUS_MAP = {
    "incomplete": "incomplete",
    "incomplete_expired": "canceled",
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "past_due",
}

WEBHOOK_TOLERANCE_SECONDS = 300


class PolarNotConfigured(RuntimeError):
    """Raised when no API token is configured on the server."""


class SignatureError(ValueError):
    """Raised when a webhook signature does not match the raw body."""


def _active_subscription(user) -> Subscription | None:
    subscription = getattr(user, "subscription", None)
    if subscription is None:
        return None
    if subscription.status in ACTIVE_STATUSES:
        return subscription
    if (
        subscription.status in GRACE_STATUSES
        and subscription.current_period_end
        and subscription.current_period_end > timezone.now()
    ):
        return subscription
    return None


def get_plan_name(user) -> str:
    subscription = _active_subscription(user)
    return subscription.plan if subscription else "free"


def monitors_limit(user) -> int:
    return PLANS[get_plan_name(user)]["monitors"]


def min_interval(user) -> int:
    return PLANS[get_plan_name(user)]["min_interval"]


def status_pages_limit(user) -> int | None:
    return PLANS[get_plan_name(user)]["status_pages"]


def channels_limit(user) -> int | None:
    return PLANS[get_plan_name(user)]["channels"]


def can_add_monitor(user) -> tuple[bool, str]:
    count = user.monitors.count()
    limit = monitors_limit(user)
    if count >= limit:
        return False, f"Plan limit reached ({count}/{limit} monitors). Upgrade to add more."
    return True, ""


def can_add_status_page(user) -> tuple[bool, str]:
    limit = status_pages_limit(user)
    if limit is None:
        return True, ""
    count = user.status_pages.count()
    if count >= limit:
        return False, f"Plan limit reached ({count}/{limit} status pages). Upgrade to add more."
    return True, ""


def can_add_channel(user) -> tuple[bool, str]:
    limit = channels_limit(user)
    if limit is None:
        return True, ""
    count = user.notification_channels.count()
    if count >= limit:
        return False, f"Plan limit reached ({count}/{limit} notification channels). Upgrade to add more."
    return True, ""


def get_plan_summary(user) -> dict:
    subscription = _active_subscription(user)
    plan = get_plan_name(user)
    return {
        "plan": plan,
        "label": PLANS[plan]["label"],
        "monitors_used": user.monitors.count(),
        "monitors_limit": monitors_limit(user),
        "status_pages_limit": status_pages_limit(user),
        "channels_limit": channels_limit(user),
        "subscription_status": subscription.status if subscription else "active",
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription is not None and subscription.current_period_end
            else None
        ),
    }


def polar_headers() -> dict:
    if not settings.POLAR_ACCESS_TOKEN:
        raise PolarNotConfigured("Polar is not configured on this server.")
    return {
        "Authorization": f"Bearer {settings.POLAR_ACCESS_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _frontend_url(path: str = "") -> str:
    origin = getattr(settings, "FRONTEND_URL", None) or "http://localhost:5173"
    return origin + path


def create_checkout_session(user, plan: str) -> str:
    """Create a Polar Checkout Session URL for one of our paid plans."""
    if plan not in ("pro", "business"):
        raise ValueError("Unknown plan.")
    product_id = PLANS[plan]["product_id"]
    if not product_id:
        raise ValueError("Polar product for this plan is not configured.")
    body = {
        "product_id": product_id,
        "success_url": _frontend_url("/dashboard?billing=success"),
        "customer_email": user.email,
        "metadata": {"user_id": str(user.pk), "plan": plan},
        "customer_metadata": {"user_id": str(user.pk)},
        "allow_discount_codes": True,
    }
    response = httpx.post(
        f"{settings.POLAR_API_BASE}/checkout-sessions",
        json=body,
        headers=polar_headers(),
        timeout=20,
    )
    response.raise_for_status()
    url = response.json()["url"]
    logger.info("polar checkout created: user=%s plan=%s", user.pk, plan)
    return url


def create_portal_session(user) -> str:
    """Create a Polar Customer Session and return its portal URL."""
    if not user.polar_customer_id:
        raise ValueError("No active subscription — subscribe first.")
    response = httpx.post(
        f"{settings.POLAR_API_BASE}/customer-sessions",
        json={"customer_id": user.polar_customer_id},
        headers=polar_headers(),
        timeout=20,
    )
    response.raise_for_status()
    url = response.json().get("customer_portal_url")
    if not url:
        raise ValueError("Polar did not return a customer portal URL.")
    return url


def verify_signature(request_body: bytes, headers: Mapping[str, str]) -> None:
    """Verify a Polar webhook using the Standard Webhooks HMAC scheme."""
    secret = settings.POLAR_WEBHOOK_SECRET
    if not secret:
        raise PolarNotConfigured("Webhook verification is not configured.")
    msg_id = headers.get("webhook-id", "")
    timestamp = headers.get("webhook-timestamp", "")
    signature_header = headers.get("webhook-signature", "")
    if not (msg_id and timestamp and signature_header):
        raise SignatureError("Missing webhook signature headers.")
    try:
        ts = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise SignatureError("Invalid webhook timestamp.") from exc
    if abs(time.time() - ts) > WEBHOOK_TOLERANCE_SECONDS:
        raise SignatureError("Webhook timestamp outside tolerance.")

    # Standard Webhooks: the secret is base64 after the optional whsec_ prefix.
    raw_secret = secret[6:] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(raw_secret, validate=True)
    except (binascii.Error, ValueError):
        key = secret.encode()

    signed_content = f"{msg_id}.{timestamp}.".encode() + request_body
    expected = base64.b64encode(
        hmac.new(key, signed_content, hashlib.sha256).digest()
    ).decode()
    for part in signature_header.split():
        version, _, provided = part.partition(",")
        if version == "v1" and hmac.compare_digest(expected, provided):
            return
    raise SignatureError("Invalid signature.")


def _plan_for_product(product_id: Any) -> str | None:
    wanted = str(product_id or "")
    if not wanted:
        return None
    for plan, config in PLANS.items():
        if config["product_id"] and str(config["product_id"]) == wanted:
            return plan
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _status_for(polar_status: str):
    from .models import Subscription

    return _STATUS_MAP.get(polar_status or "", Subscription.Status.PAST_DUE)


def _resolve_user(event: dict):
    from accounts.models import User

    data = event.get("data", {}) or {}
    metadata = data.get("metadata") or {}
    user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user is not None:
            return user
    email = (data.get("customer") or {}).get("email")
    if email:
        return User.objects.filter(email__iexact=str(email)).first()
    return None


def handle_webhook_event(event: dict, delivery_id: str = "") -> None:
    """Sync a verified Polar event into Subscription rows, idempotently.

    The ``WebhookEvent`` row claims each delivery id inside a transaction
    (FOR UPDATE) before applying; duplicate deliveries of an already-processed
    id are skipped, matching Polar's at-least-once delivery semantics.
    """
    from django.db import transaction

    from .models import WebhookEvent

    event_type = event.get("type", "")
    if not delivery_id:
        logger.warning("polar webhook: delivery without webhook-id — applying without idempotency")
        _apply_event(event)
        return

    with transaction.atomic():
        webhook_event, created = WebhookEvent.objects.select_for_update().get_or_create(
            id=delivery_id,
            defaults={"provider": "polar", "type": event_type, "payload": event},
        )
        if not created and webhook_event.processed_at is not None:
            logger.info("webhook %s: duplicate delivery skipped", delivery_id)
            return
        _apply_event(event)
        audit_log(
            None,
            "billing.webhook_processed",
            user=None,
            event_id=delivery_id,
            event_type=event_type,
        )
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["processed_at"])


def _apply_event(event: dict) -> None:
    """Apply a verified Polar event to Subscription rows (no idempotency)."""
    from .models import Subscription

    event_type = event.get("type", "")
    data = event.get("data", {}) or {}
    subscription_id = str(data.get("id") or "")
    product_id = str(data.get("product_id") or "")
    customer_id = str(data.get("customer_id") or "")
    customer = data.get("customer") or {}

    if event_type in ("subscription.created", "subscription.updated", "subscription.active"):
        subscription = (
            Subscription.objects.filter(polar_subscription_id=subscription_id).first()
            if subscription_id
            else None
        )
        if subscription is None:
            user = _resolve_user(event)
            if user is None:
                logger.warning(
                    "polar webhook %s: no user for sub=%s email=%s",
                    event_type,
                    subscription_id,
                    customer.get("email"),
                )
                return
            subscription, _ = Subscription.objects.get_or_create(user=user)

        plan = _plan_for_product(product_id)
        if plan is None:
            plan = (data.get("metadata") or {}).get("plan")
            if plan not in PLANS:
                plan = subscription.plan if subscription.plan in PLANS else "pro"

        subscription.plan = plan
        subscription.status = _status_for(data.get("status", "active"))
        subscription.polar_subscription_id = subscription_id
        subscription.polar_customer_id = customer_id
        subscription.polar_product_id = product_id
        subscription.current_period_end = _parse_datetime(
            data.get("current_period_end") or data.get("ends_at")
        )
        subscription.save()

        if customer_id:
            user = subscription.user
            if user.polar_customer_id != customer_id:
                user.polar_customer_id = customer_id
                user.save(update_fields=["polar_customer_id"])

        logger.info(
            "polar webhook %s: sub=%s user=%s plan=%s status=%s",
            event_type,
            subscription_id,
            subscription.user.pk,
            subscription.plan,
            subscription.status,
        )
        return

    if event_type in ("subscription.canceled", "subscription.revoked"):
        subscription = Subscription.objects.filter(
            polar_subscription_id=subscription_id
        ).first()
        if subscription is None:
            return
        if event_type == "subscription.revoked":
            # Access is revoked immediately — drop to Free.
            subscription.status = Subscription.Status.CANCELED
            subscription.plan = "free"
            subscription.current_period_end = None
        else:
            # Canceled but still paid until the period ends (grace window).
            subscription.status = Subscription.Status.CANCELED
            subscription.current_period_end = _parse_datetime(
                data.get("current_period_end") or data.get("ends_at")
            )
        subscription.save(update_fields=["status", "plan", "current_period_end", "updated_at"])
        logger.info(
            "polar webhook %s: sub=%s user=%s -> %s",
            event_type,
            subscription_id,
            subscription.user.pk,
            subscription.status,
        )
        return

    if event_type == "subscription.past_due":
        subscription = Subscription.objects.filter(
            polar_subscription_id=subscription_id
        ).first()
        if subscription is None:
            return
        subscription.status = Subscription.Status.PAST_DUE
        subscription.save(update_fields=["status", "updated_at"])
        logger.warning(
            "polar webhook past_due: sub=%s user=%s", subscription_id, subscription.user.pk
        )

