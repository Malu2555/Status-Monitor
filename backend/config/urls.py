"""URL configuration for the Status Monitor project."""

from django.conf import settings
from django.contrib import admin
from django.urls import path

from config.api import api

urlpatterns = [
    path("api/", api.urls),
]

# The Django admin is opt-in (ADMIN_ENABLED) and mounted at an env-configured
# path. When disabled the URL simply does not exist (404, no information leak).
if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path(settings.ADMIN_PATH.lstrip("/"), admin.site.urls))
