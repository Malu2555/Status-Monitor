"""Project app config: swaps in the hardened admin site."""

from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps


class Config(AppConfig):
    """Plain project app (hosts the export_openapi management command)."""

    name = "config"
    default = True


class SecureAdminConfig(admin_apps.AdminConfig):
    default_site = "accounts.admin_site.SecureAdminSite"
    default = False
