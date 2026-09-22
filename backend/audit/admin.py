from django.contrib import admin

from .models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "kind", "user", "ip", "payload")
    list_filter = ("kind",)
    search_fields = ("kind", "user__username", "ip")
    readonly_fields = [field.name for field in AuditLogEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
