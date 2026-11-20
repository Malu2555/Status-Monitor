from django.conf import settings
from django.db import models


class MonitorNotificationChannel(models.Model):
    """One delivery target (email, webhook, Slack, Discord or Telegram) for one monitor."""

    class Kind(models.TextChoices):
        EMAIL = "email", "Email"
        WEBHOOK = "webhook", "Webhook"
        SLACK = "slack", "Slack"
        DISCORD = "discord", "Discord"
        TELEGRAM = "telegram", "Telegram"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_channels",
    )
    monitor = models.ForeignKey(
        "monitors.Monitor",
        on_delete=models.CASCADE,
        related_name="notification_channels",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    address = models.CharField(max_length=500)  # email address or webhook URL
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["monitor", "kind", "address"],
                name="unique_monitor_channel",
            )
        ]

    def __str__(self):
        return f"{self.monitor} → {self.kind}:{self.address}"


class NotificationDelivery(models.Model):
    """Outbox row: one state-transition event headed to one channel."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DEAD = "dead", "Dead"

    monitor = models.ForeignKey(
        "monitors.Monitor",
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
    )
    channel = models.ForeignKey(
        MonitorNotificationChannel,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_kind = models.CharField(max_length=16)  # "down" | "up" | "ssl"
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.monitor} {self.event_kind} via {self.channel.kind} [{self.status}]"
