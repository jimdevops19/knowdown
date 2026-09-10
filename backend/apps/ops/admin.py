"""Who opened the admin, when, and for how long — readable from inside it.

Read-only on purpose. Closing a window is `manage.py close_admin`; a Delete
button here would let a session end itself mid-click, and the row is the audit
trail of an access that happened, so it should not be editable by the access.
"""

from __future__ import annotations

from django.contrib import admin

from .models import AdminWindow


@admin.register(AdminWindow)
class AdminWindowAdmin(admin.ModelAdmin):
    list_display = ("created_at", "opened_by", "expires_at", "closed_at", "is_live")
    readonly_fields = ("token_hash", "opened_by", "created_at", "expires_at", "closed_at")

    @admin.display(boolean=True, description="Live")
    def is_live(self, obj: AdminWindow) -> bool:
        return obj.is_live

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
