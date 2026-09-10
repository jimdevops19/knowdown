from django.contrib import admin

from .models import Player


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "is_bot", "has_auto_name", "created_at")
    list_filter = ("has_auto_name", "is_bot")
    search_fields = ("display_name",)
    # The name is written by `services.set_display_name` and nowhere else — an
    # admin form that edited it directly would be the one path around the
    # validator and the uniqueness message.
    readonly_fields = ("display_name", "has_auto_name", "created_at", "updated_at")
    raw_id_fields = ("user",)
