from django.contrib import admin

from .models import MonitorNotificationChannel, NotificationDelivery


@admin.register(MonitorNotificationChannel)
class MonitorNotificationChannelAdmin(admin.ModelAdmin):
    list_display = ("monitor", "user", "kind", "address", "enabled", "created_at")
    list_filter = ("kind", "enabled")
    search_fields = ("address", "monitor__name", "user__username")


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("monitor", "channel", "event_kind", "status", "attempts", "created_at", "sent_at")
    list_filter = ("status", "event_kind")
    search_fields = ("monitor__name", "channel__address")
    readonly_fields = (
        "monitor",
        "channel",
        "event_kind",
        "payload",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "sent_at",
    )

    def has_add_permission(self, request):
        return False
