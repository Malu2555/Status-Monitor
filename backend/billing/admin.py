from django.contrib import admin

from .models import Subscription, WebhookEvent


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "status",
        "polar_subscription_id",
        "current_period_end",
        "updated_at",
    )
    list_filter = ("plan", "status")
    search_fields = ("user__username", "user__email")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "type", "received_at", "processed_at")
    list_filter = ("provider", "type")
    search_fields = ("id", "type")
    readonly_fields = ("id", "provider", "type", "payload", "processed_at", "received_at")

    def has_add_permission(self, request):
        return False

