from django.contrib import admin

from .models import Check, Monitor


@admin.register(Monitor)
class MonitorAdmin(admin.ModelAdmin):
    list_display = ("name", "url", "owner", "last_status", "last_checked_at", "is_public", "is_active", "is_system")
    list_filter = ("last_status", "is_public", "is_active", "is_system")
    search_fields = ("name", "url")


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    list_display = ("monitor", "is_up", "status_code", "response_ms", "checked_at")
    list_filter = ("is_up", "checked_at")
    search_fields = ("monitor__name",)
