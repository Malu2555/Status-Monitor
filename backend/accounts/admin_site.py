"""Admin site configuration: Django admin is superuser-only and 2FA-gated.

The default AdminSite only checks ``is_staff``. In this project ``is_staff`` is
also the credential used by the moderation API, so we deliberately require
``is_superuser`` plus a verified TOTP device (django-otp) for the admin UI.
"""

import logging
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django_otp import devices_for_user
from django_otp.admin import OTPAdminAuthenticationForm, OTPAdminSite

from accounts import abuse
from audit.services import audit_log

from .security import notify_admin

logger = logging.getLogger("accounts")


def _bump(key: str, window: int) -> int:
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        return 1
    except Exception as exc:  # cache table missing/unavailable must not 500 logins
        logger.warning("admin login counter unavailable: %s", exc)
        return 0


class SecureAdminSite(OTPAdminSite):
    """Superuser-only, TOTP-gated Django admin."""

    name = "admin"
    login_form: Any = None  # assigned below

    def has_permission(self, request):
        user = request.user
        verified = getattr(user, "is_verified", lambda: False)()
        return bool(getattr(user, "is_active", False) and getattr(user, "is_superuser", False) and verified)


class RateLimitedOTPAdminAuthenticationForm(OTPAdminAuthenticationForm):
    """Admin login form with OTP + failure lockout.

    ``OTPAdminAuthenticationForm`` already refuses users without a verified
    TOTP device, so a successful ``clean()`` means password + OTP both passed.
    """

    request: Any
    user_cache: Any

    def _chosen_device(self, user):
        """Auto-select the user's only confirmed device (one-step admin login)."""
        device = super()._chosen_device(user)
        if device is None:
            devices = list(devices_for_user(user, confirmed=True))
            if len(devices) == 1:
                device = devices[0]
        return device

    def clean(self):
        try:
            cleaned = super().clean()
        except ValidationError as exc:
            # Selecting a device is UX, not a credential failure: don't lock an
            # admin who simply has more than one confirmed device.
            if any(getattr(error, "code", "") == "device_required" for error in exc.error_list):
                raise
            self._record_failure()
            raise
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return cleaned

    def _client_ip(self) -> str:
        try:
            return abuse.client_ip(self.request)
        except Exception:
            return ""

    def _audit_ip(self) -> dict:
        return {
            "remote": self.request.META.get("REMOTE_ADDR", "")[:64],
            "xff": self.request.META.get("HTTP_X_FORWARDED_FOR", "")[:300],
        }

    def _record_failure(self) -> None:
        ip = self._client_ip()
        username = str(self.data.get("username", ""))[:150]
        threshold = settings.ADMIN_LOGIN_MAX_FAILURES
        window = settings.ADMIN_LOGIN_LOCK_WINDOW

        ip_count = _bump(f"admin:fail:ip:{ip or 'unknown'}", window) if ip else 0
        _bump(f"admin:fail:user:{username or 'unknown'}", window)

        logger.warning(
            "admin login failed: ip=%s username=%s attempts=%s",
            ip,
            username,
            ip_count,
        )
        audit_log(self.request, "admin.login_failed", username=username, **self._audit_ip())

        if ip and ip_count >= threshold:
            abuse.block_ip(
                ip,
                reason=f"admin login failures ({ip_count})",
                auto=True,
                seconds=settings.ADMIN_LOGIN_LOCK_SECONDS,
            )
            notify_admin(
                "Admin login blocked",
                f"{ip} was blocked after {ip_count} failed admin logins (last username: {username or 'unknown'}).",
            )

        if settings.ADMIN_LOGIN_DELAY_SECONDS > 0:
            time.sleep(settings.ADMIN_LOGIN_DELAY_SECONDS)

    def _record_success(self) -> None:
        user = getattr(self, "user_cache", None)
        if user is None:
            return
        ip = self._client_ip()
        # A successful login clears the failure streak for this IP/username.
        cache.delete(f"admin:fail:ip:{ip or 'unknown'}")
        cache.delete(f"admin:fail:user:{getattr(user, 'username', '') or 'unknown'}")
        audit_log(self.request, "admin.login_success", user=user, ip=ip or None, **self._audit_ip())
        logger.info("admin login ok: user=%s ip=%s", user.username, ip)

        if ip:
            key = f"admin:last_ip:{user.pk}"
            previous = cache.get(key)
            if previous and previous != ip:
                notify_admin(
                    "Admin login from a new IP",
                    f"{user.username} signed into the admin from {ip} (previous: {previous}).",
                )
            cache.set(key, ip, 60 * 60 * 24 * 30)


SecureAdminSite.login_form = RateLimitedOTPAdminAuthenticationForm
