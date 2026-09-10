from django.contrib import admin

from .models import Ranking


@admin.register(Ranking)
class RankingAdmin(admin.ModelAdmin):
    list_display = ("player", "category", "rating", "wins", "losses", "games_played")
    list_filter = ("category",)
    search_fields = ("player__display_name",)
    raw_id_fields = ("player", "category")
    # Written only by `services.ratings.update_ratings_for_matchup` and
    # `ensure_ranking` — an admin form that edited these directly would be a
    # second, untracked way for a ladder to move.
    readonly_fields = ("rating", "wins", "losses", "games_played")
