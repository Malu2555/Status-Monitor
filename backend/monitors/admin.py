from django.contrib import admin

from .models import Check, Incident, MaintenanceWindow, Monitor


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


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("monitor", "started_at", "ended_at", "checks_down", "last_status_code")
    list_filter = ("monitor",)
    search_fields = ("monitor__name",)


@admin.register(MaintenanceWindow)
class MaintenanceWindowAdmin(admin.ModelAdmin):
    list_display = ("monitor", "starts_at", "ends_at", "note", "created_at")
    list_filter = ("monitor",)
    search_fields = ("monitor__name", "note")
