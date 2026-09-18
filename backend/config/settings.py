"""
Django settings for the Status Monitor project.

All secrets and configuration come from environment variables (.env file).
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key")
DEBUG = os.environ.get("DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "accounts",
    "monitors",
    "billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
ACCESS_TOKEN_LIFETIME = timedelta(minutes=int(os.environ.get("ACCESS_TOKEN_MINUTES", "15")))
REFRESH_TOKEN_LIFETIME = timedelta(days=int(os.environ.get("REFRESH_TOKEN_DAYS", "7")))

COOKIE_REFRESH_NAME = "sm_refresh"
COOKIE_CSRF_NAME = "sm_csrf"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "False").lower() in ("1", "true", "yes")

# Throttling bucket checks are disabled while the test runner is active.
DISABLE_THROTTLING = "test" in sys.argv

# --------------------------------------------------------------------------
# CORS — credentials allowed, explicit allow-list only (never '*').
# --------------------------------------------------------------------------
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
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

# --------------------------------------------------------------------------
# Stripe billing
# --------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_IDS = {
    "pro": os.environ.get("STRIPE_PRICE_PRO", ""),
    "business": os.environ.get("STRIPE_PRICE_BUSINESS", ""),
}
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

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
    },
}

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

