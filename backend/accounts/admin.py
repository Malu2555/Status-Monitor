from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from audit.services import audit_log

from . import services as auth_services
from .models import AbuseEvent, BlockedIP, Policy, RevokedRefreshToken, User


@admin.register(User)
class StatusMonitorUserAdmin(UserAdmin):
    """Adds moderation controls (disable/enable) on top of the stock admin."""

    list_display = (
        "username",
        "email",
        "is_active",
        "disabled_reason",
        "plan_hint",
        "date_joined",
    )
    list_filter = ("is_active", "disabled_reason", "is_staff")
    search_fields = ("username", "email")
    fieldsets = (
        *(UserAdmin.fieldsets or ()),
        (
            "Moderation",
            {"fields": ("disabled_reason", "disabled_at")},
        ),
        (
            "Legal",
            {"fields": ("tos_accepted_at", "tos_version", "age_confirmed_at")},
        ),
    )
    actions = ("disable_accounts", "enable_accounts")

    @admin.display(description="plan")
    def plan_hint(self, obj):
        from billing.services import get_plan_name

        return get_plan_name(obj)

    @admin.action(description="Disable selected accounts (Terms violation)")
    def disable_accounts(self, request, queryset):
        total = 0
        for user in queryset.exclude(pk=request.user.pk):
            paused = auth_services.disable_user(user, "tos_violation")
            total += paused
            audit_log(
                None,
                "moderation.user_disabled",
                user=user,
                reason="tos_violation",
                by=request.user.username or "admin",
                monitors_paused=paused,
                channel="django-admin",
            )
        self.message_user(request, f"Disabled {queryset.count()} account(s); paused {total} monitor(s).")

    @admin.action(description="Re-enable selected accounts")
    def enable_accounts(self, request, queryset):
        total = 0
        for user in queryset.filter(is_active=False):
            total += auth_services.enable_user(user)
            audit_log(
                None,
                "moderation.user_enabled",
                user=user,
                by=request.user.username or "admin",
                monitors_resumed=total,
                channel="django-admin",
            )
        self.message_user(request, f"Re-enabled accounts; resumed {total} monitor(s).")


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ("slug", "version", "title", "effective_at", "created_at")
    list_filter = ("slug",)
    search_fields = ("slug", "version", "title")


@admin.register(BlockedIP)
class BlockedIPAdmin(admin.ModelAdmin):
    list_display = ("ip", "auto", "reason", "created_at", "expires_at")
    list_filter = ("auto",)
    search_fields = ("ip", "reason")
    actions = ("unblock_ips",)

    @admin.action(description="Unblock selected IPs")
    def unblock_ips(self, request, queryset):
        count, _ = queryset.delete()
        self.message_user(request, f"Removed {count} block(s).")


@admin.register(AbuseEvent)
class AbuseEventAdmin(admin.ModelAdmin):
    list_display = ("kind", "ip", "created_at")
    list_filter = ("kind",)
    search_fields = ("ip",)
    readonly_fields = ("kind", "ip", "payload", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(RevokedRefreshToken)
class RevokedRefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("jti", "user", "expires_at", "created_at")
    readonly_fields = ("jti", "user", "expires_at", "created_at")
