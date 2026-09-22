from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    stripe_customer_id = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return self.username


class AccountActionToken(models.Model):
    """Single-use, expiring token backing email verification / password reset."""

    id = models.CharField(primary_key=True, max_length=64)  # token_urlsafe(32)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_tokens",
    )
    purpose = models.CharField(max_length=24)  # "verify_email" | "password_reset"
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "purpose"])]

    def __str__(self):
        return f"{self.purpose} token for {self.user}"


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
