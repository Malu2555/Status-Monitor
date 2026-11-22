from django.contrib import admin

from .models import (
    BrokenLink,
    Check,
    CrawlRun,
    DomainRegistration,
    Incident,
    MaintenanceWindow,
    Monitor,
    SslCertificate,
    StatusPage,
)


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


@admin.register(SslCertificate)
class SslCertificateAdmin(admin.ModelAdmin):
    list_display = ("monitor", "days_remaining", "not_after", "alert_level", "checked_at")
    list_filter = ("alert_level",)
    search_fields = ("monitor__name", "subject", "issuer")
    readonly_fields = ("checked_at",)


@admin.register(StatusPage)
class StatusPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "owner", "is_public", "is_active", "updated_at")
    list_filter = ("is_public", "is_active")
    search_fields = ("title", "slug", "owner__username")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("monitors",)


@admin.register(DomainRegistration)
class DomainRegistrationAdmin(admin.ModelAdmin):
    list_display = ("monitor", "domain", "expires_at", "days_remaining", "status", "alert_level")
    list_filter = ("status", "alert_level")
    search_fields = ("domain", "monitor__name")
    readonly_fields = ("checked_at",)


@admin.register(CrawlRun)
class CrawlRunAdmin(admin.ModelAdmin):
    list_display = ("monitor", "started_at", "finished_at", "pages_crawled", "broken_count")
    list_filter = ("monitor",)
    search_fields = ("monitor__name",)
    readonly_fields = ("started_at",)


@admin.register(BrokenLink)
class BrokenLinkAdmin(admin.ModelAdmin):
    list_display = ("monitor", "target_url", "status_code", "last_seen_at", "resolved_at")
    list_filter = ("monitor", "resolved_at")
    search_fields = ("target_url", "source_url", "monitor__name")
    readonly_fields = ("first_seen_at", "last_seen_at")
