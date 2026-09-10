from django.contrib import admin

from .models import Achievement, PlayerAchievement


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")


@admin.register(PlayerAchievement)
class PlayerAchievementAdmin(admin.ModelAdmin):
    list_display = ("player", "achievement", "earned_at")
    list_filter = ("achievement",)
    search_fields = ("player__display_name",)
    raw_id_fields = ("player", "achievement")
    # Written only by services.evaluation.award_achievements_for_matchup.
    readonly_fields = ("player", "achievement", "earned_at")
