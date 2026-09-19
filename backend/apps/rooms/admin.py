"""The admin view of the lobby — read-mostly, like the question catalog's.

Rooms come from ``resources/rooms.yaml`` via ``manage.py sync_rooms``, so the
admin is here to *look at* what a sync produced (and to switch a room off in a
hurry), not as a second authoring surface: a room edited here is silently
overwritten by the next sync, which is the resource file being the source of
truth working as intended.
"""

from django.contrib import admin

from .models import Room, RoomCategory


class RoomCategoryInline(admin.TabularInline):
    model = RoomCategory
    extra = 0
    fields = ("order", "category", "filter_tags")
    ordering = ("order",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [RoomCategoryInline]
