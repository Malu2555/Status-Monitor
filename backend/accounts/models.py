from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    # Polar.sh billing identifier (merchant of record).
    polar_customer_id = models.CharField(max_length=64, blank=True, default="")

    # Proof-of-consent: when the user accepted the terms and which version.
    tos_accepted_at = models.DateTimeField(null=True, blank=True)
    tos_version = models.CharField(max_length=16, blank=True, default="")
    age_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Moderation: is_active=False is the kill switch; these record why/when.
    disabled_reason = models.CharField(
        max_length=24,
        blank=True,
        default="",
        choices=[
            ("manual", "Manual"),
            ("tos_violation", "Terms violation"),
            ("abuse", "Abuse / scanning"),
            ("chargeback", "Chargeback"),
        ],
    )
    disabled_at = models.DateTimeField(null=True, blank=True)
    # Monitors auto-paused by moderation — resumed when the account is re-enabled.
    paused_monitor_ids = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.username


class Policy(models.Model):
    """Versioned legal text served publicly (terms, privacy, acceptable use)."""
    slug = models.CharField(max_length=32)  # "terms" | "privacy" | "aup"
    version = models.CharField(max_length=16)
    title = models.CharField(max_length=200)
    body_md = models.TextField()
    effective_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["slug", "version"], name="unique_policy_version")
        ]

    def __str__(self):
        return f"{self.slug} v{self.version}"


class BlockedIP(models.Model):
    """Manual (or automatic) IP block — application-level DoS guard.

    A non-expired row makes ``BlockedIPMiddleware`` answer 403 before any view
    runs, so a hostile client costs one indexed lookup instead of a request.
    """

    ip = models.CharField(max_length=45, unique=True)
    reason = models.CharField(max_length=120, blank=True, default="")
    auto = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def is_expired(self, now=None) -> bool:
        if self.expires_at is None:
            return False
        return (now or timezone.now()) >= self.expires_at

    def __str__(self):
        suffix = " (auto)" if self.auto else ""
        return f"{self.ip}{suffix} — {self.reason or 'blocked'}"


class AbuseEvent(models.Model):
    """Observable suspicious-traffic counter (honeypot hits, auth failures)."""

    kind = models.CharField(max_length=32, db_index=True)  # honeypot | login | otp | register
    ip = models.CharField(max_length=45, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["ip", "-created_at"])]

    def __str__(self):
        return f"{self.kind} @ {self.ip or 'unknown'}"


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


class ApiToken(models.Model):
    """Hashed API token for programmatic access (sent as ``X-API-Key``).

    The plaintext token is shown exactly once at creation; only its SHA-256
    hash is stored. Tokens are scoped ``read`` or ``write``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens"
    )
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12)  # first chars, for display only
    hashed_key = models.CharField(max_length=64, unique=True)
    scope = models.CharField(max_length=8, default="write")  # "read" | "write"
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"


class RecoveryCode(models.Model):
    """One-time 2FA recovery code (stored as a SHA-256 hash)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes"
    )
    hashed_code = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["user", "used_at"])]

    def __str__(self):
        state = "used" if self.used_at else "unused"
        return f"recovery code for {self.user} ({state})"
