from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import RevokedRefreshToken, User

admin.site.register(User, UserAdmin)


@admin.register(RevokedRefreshToken)
class RevokedRefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("jti", "user", "expires_at", "created_at")
    readonly_fields = ("jti", "user", "expires_at", "created_at")
