from django.conf import settings
from django.db import models


class AuditLogEntry(models.Model):
    """Append-only trail of security- and billing-relevant actions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    kind = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict)
    ip = models.GenericIPAddressField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["user", "-occurred_at"]),
            models.Index(fields=["kind", "-occurred_at"]),
        ]

    def __str__(self):
        return f"{self.kind} @ {self.occurred_at:%Y-%m-%d %H:%M}"
