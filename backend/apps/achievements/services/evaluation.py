"""Which badges a finished matchup earns — checked in one place, from the
result alone.

**The rule that matters:** an achievement is checked from here, and only from
here, never sprinkled through ``apps.matches.services``. ``ACHIEVEMENT_RULES``
is the one registry a new badge joins — a slug in ``constants``, an entry in
``resources/achievements.yaml``, and a function here, the same three-place
pattern ``apps.questions`` uses for a new question type.

``award_achievements_for_matchup`` is the hook ``apps.matches.services`` calls
from both ``complete_matchup`` and ``abandon_matchup`` — the two ways a
matchup becomes terminal — **before** ``apps.rankings.services
.update_ratings_for_matchup``: "Beat a Higher Rated Player" reads each side's
``Ranking`` as it stands going into this result, and the rating update is what
moves it. Every other rule is indifferent to the order.

Awarding is idempotent the way ``apps.rankings``' rating update needs no
idempotency guard of its own: ``PlayerAchievement``'s unique constraint backs
a ``get_or_create``, so a matchup that cannot be completed twice (both
callers already refuse a repeat) cannot grant "First Win" twice either.
"""

from __future__ import annotations

from collections.abc import Callable

from django.db import transaction

from apps.achievements import constants
from apps.achievements.models import Achievement, PlayerAchievement
from apps.matches import selectors as match_selectors
from apps.matches.constants import DEFAULT_PLAYER_RATING, PLAYERS_PER_MATCHUP
from apps.matches.models import Matchup, MatchupPlayer, PlayerAnswer
from apps.players.models import Player
from apps.rankings.models import Ranking
from shared.logging import get_logger, labels

logger = get_logger(__name__)

__all__ = ["ACHIEVEMENT_RULES", "award_achievements_for_matchup"]


# --- Reads the rules are built from -------------------------------------------


def _total_wins(*, player: Player) -> int:
    return MatchupPlayer.objects.filter(player=player, is_winner=True).count()


def _current_win_streak(*, player: Player) -> int:
    """How many of the player's most recent completed matchups were won, in a
    row, most recent first. Capped at reading ``WIN_STREAK_TARGET`` rows —
    once that many in a row are wins the badge is earned, and a longer streak
    does not need to be counted exactly."""
    recent = (
        MatchupPlayer.objects.filter(
            player=player, matchup__status=Matchup.Status.COMPLETED
        )
        .order_by("-matchup__completed_at")
        .values_list("is_winner", flat=True)[: constants.WIN_STREAK_TARGET]
    )
    streak = 0
    for won in recent:
        if not won:
            break
        streak += 1
    return streak


def _questions_answered(*, player: Player) -> int:
    return PlayerAnswer.objects.filter(player=player).count()


def _rating_before(*, player: Player, matchup: Matchup) -> int:
    """The player's rating in ``matchup.category`` as it stood going into this
    result. Read directly rather than through ``rankings.services
    .ensure_ranking``: a player with no row yet has never played the category
    before, so they entered at the default — and reading here must not
    *create* the row before ``update_ratings_for_matchup`` does, or that call's
    own "first row" logging would be wrong."""
    entry = Ranking.objects.filter(player=player, category=matchup.category).first()
    return entry.rating if entry is not None else DEFAULT_PLAYER_RATING


def _beat_higher_rated(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    if not side.is_winner:
        return False
    opponent_side = match_selectors.opponent_of(matchup=matchup, player=player)
    return _rating_before(player=opponent_side.player, matchup=matchup) > _rating_before(
        player=player, matchup=matchup
    )


def _fastest_answer(*, matchup: Matchup, player: Player) -> bool:
    return PlayerAnswer.objects.filter(
        matchup_question__matchup=matchup,
        player=player,
        is_correct=True,
        response_time_ms__lte=constants.FASTEST_ANSWER_THRESHOLD_MS,
    ).exists()


# --- The rules themselves -----------------------------------------------------
#
# Every rule takes the same three things — the matchup, the player, and their
# own ``MatchupPlayer`` row — whether it needs all of them or not, so the
# registry below can call any of them the same way.


def _check_first_win(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return side.is_winner and _total_wins(player=player) == 1


def _check_five_wins(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return side.is_winner and _total_wins(player=player) >= 5


def _check_ten_wins(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return side.is_winner and _total_wins(player=player) >= 10


def _check_five_win_streak(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return side.is_winner and _current_win_streak(player=player) >= constants.WIN_STREAK_TARGET


def _check_perfect_match(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return side.correct_answers == matchup.question_count


def _check_hundred_questions_answered(
    *, matchup: Matchup, player: Player, side: MatchupPlayer
) -> bool:
    return _questions_answered(player=player) >= constants.QUESTIONS_ANSWERED_TARGET


def _check_fastest_answer(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return _fastest_answer(matchup=matchup, player=player)


def _check_beat_higher_rated(*, matchup: Matchup, player: Player, side: MatchupPlayer) -> bool:
    return _beat_higher_rated(matchup=matchup, player=player, side=side)


#: slug -> rule. The set of slugs this can ever award; a catalog entry whose
#: slug is not a key here loads (``sync_achievements``) but can never be
#: earned.
ACHIEVEMENT_RULES: dict[str, Callable[..., bool]] = {
    constants.FIRST_WIN: _check_first_win,
    constants.FIVE_WINS: _check_five_wins,
    constants.TEN_WINS: _check_ten_wins,
    constants.FIVE_WIN_STREAK: _check_five_win_streak,
    constants.PERFECT_MATCH: _check_perfect_match,
    constants.HUNDRED_QUESTIONS_ANSWERED: _check_hundred_questions_answered,
    constants.FASTEST_ANSWER: _check_fastest_answer,
    constants.BEAT_HIGHER_RATED: _check_beat_higher_rated,
}


# --- The hook ------------------------------------------------------------------


@transaction.atomic
def award_achievements_for_matchup(*, matchup: Matchup) -> None:
    """Check every rule against this matchup's result, once per side.

    A rule already earned is not re-run: ``PlayerAchievement.objects.filter``
    is checked first, so a cumulative rule like "Ten Wins" (which would keep
    evaluating ``True`` on every later win) is asked at most once more than it
    needs to be, never granted twice.
    """
    sides = list(matchup.players.select_related("player"))
    if len(sides) != PLAYERS_PER_MATCHUP:
        return

    active = {
        achievement.slug: achievement
        for achievement in Achievement.objects.filter(
            is_active=True, slug__in=ACHIEVEMENT_RULES
        )
    }
    if not active:
        return

    for side in sides:
        earned_slugs = set(
            PlayerAchievement.objects.filter(
                player=side.player, achievement__slug__in=active
            ).values_list("achievement__slug", flat=True)
        )
        for slug, achievement in active.items():
            if slug in earned_slugs:
                continue
            rule = ACHIEVEMENT_RULES[slug]
            if rule(matchup=matchup, player=side.player, side=side):
                _award(player=side.player, achievement=achievement)


def _award(*, player: Player, achievement: Achievement) -> None:
    _, created = PlayerAchievement.objects.get_or_create(
        player=player, achievement=achievement
    )
    if created:
        logger.info(
            f"Achievement earned: {achievement.name}", player=labels.player(player)
        )
