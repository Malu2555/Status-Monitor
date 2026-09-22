from django.contrib import admin

from .models import StripeEvent, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "stripe_subscription_id", "current_period_end", "updated_at")
    list_filter = ("plan", "status")
    search_fields = ("user__username", "user__email")


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "received_at", "processed_at")
    list_filter = ("type",)
    search_fields = ("id", "type")
    readonly_fields = ("id", "type", "payload", "processed_at", "received_at")

    def has_add_permission(self, request):
        return False
