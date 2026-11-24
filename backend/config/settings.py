"""
Django settings for the Status Monitor project.

All secrets and configuration come from environment variables (.env file).
"""

import logging
import os
import sys
import urllib.parse
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from config.env_checks import DEV_SECRET_KEY, validate_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)
DEBUG = os.environ.get("DEBUG", "True").lower() in ("1", "true", "yes")
validate_secret_key(SECRET_KEY, DEBUG)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
# Render injects RENDER_EXTERNAL_HOSTNAME; accept it automatically so a
# forgotten ALLOWED_HOSTS value doesn't take the service down.
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

INSTALLED_APPS = [
    "config.apps.SecureAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "accounts",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "monitors",
    "billing",
    "health",
    "audit",
    "notifications",
    "config",  # project package: hosts the export_openapi management command
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "config.middleware.BlockedIPMiddleware",
    "config.middleware.AdminGuardMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Database + cache (cache backs django-ninja throttling)
# --------------------------------------------------------------------------
# Development defaults to SQLite + in-memory cache (zero configuration).
# In production set DATABASE_URL to a PostgreSQL DSN; the shared cache then
# rides on the same server, so every worker/instance stays in sync. To move
# the cache to Redis later, change only the CACHES block (+ `pip install
# redis`) — nothing else touches the cache backend directly.
#   DATABASE_URL=postgres://user:password@host:5432/dbname
#   DB_CONN_MAX_AGE=60   # persistent DB connections in seconds (default 60)
_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if _DATABASE_URL:
    _parsed_url = urllib.parse.urlparse(_DATABASE_URL)
    if _parsed_url.scheme not in ("postgres", "postgresql") or not _parsed_url.path.strip("/"):
        raise ImproperlyConfigured(
            "DATABASE_URL must be a PostgreSQL DSN with a database name, e.g. postgres://user:password@host:5432/dbname"
        )
    _query = urllib.parse.parse_qs(_parsed_url.query)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": urllib.parse.unquote(_parsed_url.path.lstrip("/")),
            "USER": urllib.parse.unquote(_parsed_url.username or ""),
            "PASSWORD": urllib.parse.unquote(_parsed_url.password or ""),
            "HOST": _parsed_url.hostname or "",
            "PORT": str(_parsed_url.port or ""),
            # Persistent connections across requests; stale ones get re-tested.
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            "CONN_HEALTH_CHECKS": True,
            # Allow e.g. ?sslmode=require in the DSN (managed PG providers).
            "OPTIONS": {"sslmode": _query["sslmode"][0]} if "sslmode" in _query else {},
        }
    }
    CACHES = {
        "default": {
            # Shared across workers/instances via PostgreSQL — create the table
            # with `manage.py createcachetable` (idempotent) after migrating.
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
            # Bound table growth: oldest entries are culled probabilistically.
            "OPTIONS": {"MAX_ENTRIES": 1000},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "status-monitor",
        }
    }
    if not DEBUG:
        # WARNING+ reaches the root handler even before logging config loads,
        # so a forgotten DATABASE_URL in production is loud instead of silent.
        logging.getLogger("config").warning(
            "DATABASE_URL is not set while DEBUG=False — running on SQLite with the "
            "in-memory cache. Set DATABASE_URL to a PostgreSQL DSN for production."
        )


def _db_endpoint(db_config: dict) -> str:
    """Credential-free summary of a database config for the startup log."""
    if db_config["ENGINE"] == "django.db.backends.postgresql":
        host = db_config.get("HOST") or "localhost"
        port = f":{db_config['PORT']}" if db_config.get("PORT") else ""
        return f"postgresql {host}{port}/{db_config['NAME']}"
    return f"sqlite3 {db_config['NAME']}"


# --------------------------------------------------------------------------
# Auth / JWT
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# JWT (HS256; signed with SECRET_KEY unless a dedicated key is provided)
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "") or SECRET_KEY

# Account lifecycle token lifetimes (verification link / password-reset link)
VERIFY_EMAIL_TOKEN_TTL = timedelta(hours=int(os.environ.get("VERIFY_EMAIL_TOKEN_TTL_HOURS", "24")))
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=int(os.environ.get("PASSWORD_RESET_TOKEN_TTL_HOURS", "1")))
ACCESS_TOKEN_LIFETIME = timedelta(minutes=int(os.environ.get("ACCESS_TOKEN_MINUTES", "15")))
REFRESH_TOKEN_LIFETIME = timedelta(days=int(os.environ.get("REFRESH_TOKEN_DAYS", "7")))

COOKIE_REFRESH_NAME = "sm_refresh"
COOKIE_CSRF_NAME = "sm_csrf"
COOKIE_SECURE = env_bool("COOKIE_SECURE", default=not DEBUG)

# --------------------------------------------------------------------------
# Admin surface (Django admin is opt-in in production)
# --------------------------------------------------------------------------
# Disabled by default when DEBUG=False; enable per-session with ADMIN_ENABLED.
ADMIN_ENABLED = env_bool("ADMIN_ENABLED", default=DEBUG)
_admin_path = os.environ.get("ADMIN_PATH", "/admin/").strip().strip("/") or "admin"
ADMIN_PATH = f"/{_admin_path}/"
# Optional CIDR allow-list ("*" allows everyone, e.g. when relying on 2FA).
ADMIN_IP_ALLOWLIST = env_list("ADMIN_IP_ALLOWLIST", "")
ADMIN_LOGIN_MAX_FAILURES = int(os.environ.get("ADMIN_LOGIN_MAX_FAILURES", "5"))
ADMIN_LOGIN_LOCK_WINDOW = int(os.environ.get("ADMIN_LOGIN_LOCK_WINDOW", "900"))
ADMIN_LOGIN_LOCK_SECONDS = int(os.environ.get("ADMIN_LOGIN_LOCK_SECONDS", "3600"))
ADMIN_LOGIN_DELAY_SECONDS = float(os.environ.get("ADMIN_LOGIN_DELAY_SECONDS", "0.4"))
ADMIN_RATE_LIMIT_PER_MIN = int(os.environ.get("ADMIN_RATE_LIMIT_PER_MIN", "120"))
ADMIN_ALERT_EMAIL = os.environ.get("ADMIN_ALERT_EMAIL", "").strip()

# Application login protection (independent of IP, so a shared proxy bucket
# cannot lock every user out of one username).
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "10"))
LOGIN_LOCK_WINDOW = int(os.environ.get("LOGIN_LOCK_WINDOW", "900"))
LOGIN_LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", "600"))

# Health probes stay terse in production; set HEALTH_VERBOSE=True temporarily
# to expose component failure details to anonymous probes (debugging only).
HEALTH_VERBOSE = env_bool("HEALTH_VERBOSE", default=DEBUG)

# Short, secure admin sessions (Django's default is two weeks).
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", "1800"))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SAMESITE = "Lax"

# Shared secret for /api/admin/scheduler/* (container loop + external schedulers).
SCHEDULER_TOKEN = os.environ.get("SCHEDULER_TOKEN", "").strip()

# Throttling bucket checks are disabled while the test runner is active.
DISABLE_THROTTLING = "test" in sys.argv

# Abuse auto-block: N failures per IP inside the window -> temporary block.
AUTO_BLOCK_THRESHOLD = int(os.environ.get("AUTO_BLOCK_THRESHOLD", "50"))
AUTO_BLOCK_WINDOW_SECONDS = int(os.environ.get("AUTO_BLOCK_WINDOW_SECONDS", "3600"))
AUTO_BLOCK_FOR_SECONDS = int(os.environ.get("AUTO_BLOCK_FOR_SECONDS", str(24 * 3600)))

if DISABLE_THROTTLING:
    # django-otp throttles repeated TOTP failures (1s, 2s, 4s ...). That is a
    # wall-clock dependency, so disable it while testing.
    OTP_TOTP_THROTTLE_FACTOR = 0
    # A burst of failed logins in one test must never block the whole run.
    AUTO_BLOCK_THRESHOLD = 10**6

# --------------------------------------------------------------------------
# Request size limits — application-level DoS guard (never accept giant bodies)
# --------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024  # bytes (default is 2.5 MB)
FILE_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

# Only trust X-Forwarded-* headers from these proxies. Render/Vercel terminate
# TLS in front of the app, so their edge IPs must be listed here in production.
USE_X_FORWARDED_HOST = os.environ.get("USE_X_FORWARDED_HOST", "False").lower() in (
    "1",
    "true",
    "yes",
)
TRUSTED_PROXY_IPS = env_list("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
# Number of trusted proxy hops appended to X-Forwarded-For (1 = rightmost).
PROXY_HOPS = max(int(os.environ.get("PROXY_HOPS", "1")), 1)

# --------------------------------------------------------------------------
# CORS — credentials allowed, explicit allow-list only (never '*').
# DEBUG merges the Vite dev origins; production must list its own explicitly
# (e.g. https://<your-project>.vercel.app).
# --------------------------------------------------------------------------
CORS_ALLOW_CREDENTIALS = True
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", ",".join(_DEV_ORIGINS) if DEBUG else "")
if DEBUG:
    for _origin in _DEV_ORIGINS:
        if _origin not in CORS_ALLOWED_ORIGINS:
            CORS_ALLOWED_ORIGINS.append(_origin)
CORS_ALLOW_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-csrf-token",
    "origin",
    "user-agent",
]

# --------------------------------------------------------------------------
# Monitor checks
# --------------------------------------------------------------------------
# Self-monitor, seeded by a data migration; checked by the cron run_checks command.
SELF_MONITOR_URL = os.environ.get("SELF_MONITOR_URL", "").strip()
SELF_MONITOR_NAME = os.environ.get("SELF_MONITOR_NAME", "Status Monitor").strip()
# Hard cap on how long a single check may take (seconds).
CHECK_TIMEOUT_SECONDS = 10
# Max redirects followed, with SSRF re-validation on every hop.
CHECK_MAX_REDIRECTS = 5
# Keyword checks only inspect this much of the response body.
CHECK_MAX_BODY_BYTES = int(os.environ.get("CHECK_MAX_BODY_BYTES", "524288"))
# Broken-link crawls stop after this many seconds (keeps HTTP cron windows sane).
CRAWL_MAX_SECONDS = int(os.environ.get("CRAWL_MAX_SECONDS", "45"))

# --------------------------------------------------------------------------
# Polar.sh billing (merchant of record: handles global tax/VAT for us)
# --------------------------------------------------------------------------
POLAR_ACCESS_TOKEN = os.environ.get("POLAR_ACCESS_TOKEN", "")
POLAR_WEBHOOK_SECRET = os.environ.get("POLAR_WEBHOOK_SECRET", "")
POLAR_PRODUCT_IDS = {
    "pro": os.environ.get("POLAR_PRODUCT_PRO", ""),
    "business": os.environ.get("POLAR_PRODUCT_BUSINESS", ""),
}
POLAR_USE_SANDBOX = os.environ.get("POLAR_USE_SANDBOX", "False").lower() in ("1", "true", "yes")
POLAR_API_BASE = "https://sandbox-api.polar.sh/v1" if POLAR_USE_SANDBOX else "https://api.polar.sh/v1"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# --------------------------------------------------------------------------
# Multi-region checks + SSL certificate expiry monitoring
# --------------------------------------------------------------------------
# One runner per region; `run_checks` stamps each Check with this label so the
# dashboard can show a per-region breakdown instead of a single opinion.
REGION_NAME = os.environ.get("REGION_NAME", "local").strip() or "local"
SSL_WARN_DAYS = int(os.environ.get("SSL_WARN_DAYS", "30"))
SSL_CRITICAL_DAYS = int(os.environ.get("SSL_CRITICAL_DAYS", "7"))
# Domain registration expiry alert thresholds (days remaining).
DOMAIN_WARN_DAYS = int(os.environ.get("DOMAIN_WARN_DAYS", "30"))
DOMAIN_CRITICAL_DAYS = int(os.environ.get("DOMAIN_CRITICAL_DAYS", "7"))

# --------------------------------------------------------------------------
# Logging — our apps log at INFO to the console; framework noise stays WARNING+.
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "accounts": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "monitors": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "billing": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "health": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "notifications": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "config": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}


if DISABLE_THROTTLING:
    # Negative-path tests intentionally trigger warnings/errors; they are
    # captured with assertLogs, so keep the test output readable.
    for _logger in LOGGING["loggers"].values():
        _logger["level"] = "ERROR"
    LOGGING["loggers"]["django"] = {"level": "ERROR"}
    LOGGING["loggers"]["django.request"] = {"level": "CRITICAL"}


def _configure_logging(logging_settings: dict) -> None:
    """dictConfig, then log which database/cache backends were selected.

    Used as LOGGING_CONFIG so the summary is emitted after logging is wired
    up — settings import runs before Django configures logging, so an INFO
    line logged at import time would be dropped. The summary never includes
    the DSN (credentials): only the engine, host, port and database name.
    (Django 6.1 passes the LOGGING dict as a positional argument.)
    """
    from logging.config import dictConfig

    dictConfig(logging_settings)
    logging.getLogger("config").info(
        "startup: database=%s cache=%s sentry=%s",
        _db_endpoint(DATABASES["default"]),
        CACHES["default"]["BACKEND"],
        "enabled" if os.environ.get("SENTRY_DSN") else "disabled",
    )


LOGGING_CONFIG = "config.settings._configure_logging"

# --------------------------------------------------------------------------
# Legal / compliance — version stamped on every registration (proof of consent)
# --------------------------------------------------------------------------
TOS_VERSION = os.environ.get("TOS_VERSION", "1.0")

# --------------------------------------------------------------------------
# Email — console backend for dev; wire a real provider (SMTP/SES/…) when
# the account-lifecycle milestone lands (see .env.example).
# --------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Status Monitor <noreply@localhost>")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))

# --------------------------------------------------------------------------
# Error reporting — Sentry stays a no-op unless SENTRY_DSN is provided.
# --------------------------------------------------------------------------
if os.environ.get("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        integrations=[DjangoIntegration()],
        environment="dev" if DEBUG else "prod",
        traces_sample_rate=0.0,  # leave performance tracing off for now
        # PII is disabled by default (send_default_pii=False); keeping it implicit
        # avoids a signature drift between sentry-sdk releases.
    )

# --------------------------------------------------------------------------
# Internationalization / static
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Production hardening knobs (enable when deploying behind HTTPS)
# --------------------------------------------------------------------------
if os.environ.get("SECURE_SSL_REDIRECT", "False").lower() in ("1", "true", "yes"):
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
