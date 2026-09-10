from django.contrib import admin

from .models import Matchup, MatchupPlayer, MatchupQuestion, PlayerAnswer


class MatchupPlayerInline(admin.TabularInline):
    model = MatchupPlayer
    extra = 0
    readonly_fields = (
        "player",
        "score",
        "correct_answers",
        "total_answer_time_ms",
        "is_winner",
        "left_at",
        "joined_at",
    )
    can_delete = False


class MatchupQuestionInline(admin.TabularInline):
    model = MatchupQuestion
    extra = 0
    readonly_fields = ("order", "question_type", "question_id", "started_at", "completed_at")
    can_delete = False


@admin.register(Matchup)
class MatchupAdmin(admin.ModelAdmin):
    # Read-only everywhere: every field here is written by
    # `apps.matches.services`, never by hand — the admin is a window onto a
    # match, not a second way to referee one.
    list_display = ("id", "category", "question_count", "status", "outcome", "created_at")
    list_filter = ("status", "outcome", "category")
    readonly_fields = [f.name for f in Matchup._meta.fields]
    inlines = [MatchupPlayerInline, MatchupQuestionInline]

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(PlayerAnswer)
class PlayerAnswerAdmin(admin.ModelAdmin):
    list_display = ("matchup_question", "player", "is_correct", "points", "response_time_ms")
    list_filter = ("is_correct",)
    readonly_fields = [f.name for f in PlayerAnswer._meta.fields]
    raw_id_fields = ("matchup_question", "player")

    def has_add_permission(self, request) -> bool:
        return False
