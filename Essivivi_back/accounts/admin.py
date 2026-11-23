from django.contrib import admin

from .models import BackupCode, DeviceToken, Invitation, Permission, Role, RolePermission, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "role", "is_active", "two_factor_enabled")
    list_filter = ("role", "is_active", "two_factor_enabled")
    search_fields = ("email", "phone", "first_name", "last_name")
    exclude = ("password", "totp_secret")

    def has_add_permission(self, request):
        return False  # les comptes se créent par invitation ou inscription, jamais ici


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "status", "expires_at", "code_attempts")
    list_filter = ("status", "role")
    exclude = ("token_hash", "code_hash")


admin.site.register([Role, Permission, RolePermission, BackupCode, DeviceToken])
