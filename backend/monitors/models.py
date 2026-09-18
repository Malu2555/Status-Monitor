from django.conf import settings
from django.db import models


class Monitor(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        UP = "up", "Up"
        DOWN = "down", "Down"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="monitors",
    )
    name = models.CharField(max_length=100)
    url = models.CharField(max_length=500)
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, editable=False)
    check_interval_seconds = models.PositiveIntegerField(default=300)

    last_status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UNKNOWN
    )
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_response_ms = models.PositiveIntegerField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_interval_seconds__gte=60),
                name="monitor_interval_min_60",
            )
        ]

    def __str__(self):
        return self.name


class Check(models.Model):
    """One probe result for a monitor."""

    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="checks")
    is_up = models.BooleanField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["monitor", "-checked_at"])]

    def __str__(self):
        return f"{self.monitor.pk} {self.is_up} @ {self.checked_at}"
