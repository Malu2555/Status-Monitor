from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return self.username


class RevokedRefreshToken(models.Model):
    """Blacklist of refresh-token jti values (old tokens after rotation/logout)."""

    jti = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.CASCADE,
        related_name="revoked_tokens",
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
