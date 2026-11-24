"""Startup configuration guards — fail fast before serving traffic."""

from django.core.exceptions import ImproperlyConfigured

#: Development fallback: long enough for PyJWT (>=32 bytes, RFC 7518) and for
#: Django's own checks (>=50 chars), but obviously not a real secret.
DEV_SECRET_KEY = "dev-only-insecure-secret-change-me-" + "0" * 32
MIN_SECRET_KEY_LENGTH = 50


def validate_secret_key(secret: str, debug: bool) -> None:
    """Refuse to boot in production with the dev key or a short key."""
    if debug:
        return
    if secret == DEV_SECRET_KEY:
        raise ImproperlyConfigured(
            "SECRET_KEY is still the development default; set a random value of "
            "at least 50 characters when DEBUG=False."
        )
    if len(secret) < MIN_SECRET_KEY_LENGTH:
        raise ImproperlyConfigured(
            f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters when "
            'DEBUG=False (generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(48))").'
        )
