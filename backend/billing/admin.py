from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "stripe_subscription_id", "current_period_end", "updated_at")
    list_filter = ("plan", "status")
    search_fields = ("user__username", "user__email")
