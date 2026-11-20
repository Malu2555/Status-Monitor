from django.conf import settings
from django.db import models


class Subscription(models.Model):
    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        BUSINESS = "business", "Business"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIALING = "trialing", "Trialing"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        INCOMPLETE = "incomplete", "Incomplete"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    polar_subscription_id = models.CharField(max_length=64, blank=True, default="")
    polar_customer_id = models.CharField(max_length=64, blank=True, default="")
    polar_product_id = models.CharField(max_length=64, blank=True, default="")
    current_period_end = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} — {self.plan} ({self.status})"


class WebhookEvent(models.Model):
    """Verified billing webhook event; makes webhook processing idempotent.

    Polar.sh redelivers webhooks until they return 2xx, so the same delivery
    may arrive more than once. ``processed_at`` marks the moment the event's
    effects were applied; duplicate deliveries are skipped. ``provider`` keeps
    the ledger future-proof if we ever add a second gateway.
    """

    id = models.CharField(primary_key=True, max_length=64)  # provider delivery id
    provider = models.CharField(max_length=24, default="polar")
    type = models.CharField(max_length=128)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        state = "processed" if self.processed_at else "pending"
        return f"{self.provider}:{self.id} ({self.type}, {state})"
