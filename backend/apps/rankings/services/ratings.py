"""The match → rating pipeline: Elo, one category at a time.

Deliberately simpler than a tournament ladder's: there is no guest handling,
no race-length scaling, no competitive-vs-friendly split to decide before a
result counts, and no ``RatingChange`` audit trail to unwind. Every matchup
that reaches ``COMPLETED`` — played to the end or abandoned
(``apps.matches.models.Matchup.Outcome``) — moves both players' rating in its
category exactly once, and that is the whole pipeline.

``update_ratings_for_matchup`` is the one hook ``apps.matches.services`` calls,
from both ``complete_matchup`` and ``abandon_matchup`` — the two ways a matchup
becomes terminal — after either has already decided the winner. Neither call
site can reach this twice for the same matchup: both are idempotent against a
repeat call before they get here (see their own docstrings), so there is
nothing for this module to guard against replaying.
"""

from __future__ import annotations

from django.db import transaction

from apps.categories.models import Category
from apps.matches.constants import DEFAULT_PLAYER_RATING, PLAYERS_PER_MATCHUP
from apps.matches.models import Matchup
from apps.players.models import Player
from apps.rankings import selectors
from apps.rankings.constants import K_FACTOR
from apps.rankings.models import Ranking
from shared.logging import get_logger, labels

logger = get_logger(__name__)

__all__ = [
    "ensure_ranking",
    "expected_score",
    "seed_all_players",
    "update_rating",
    "update_ratings_for_matchup",
]


def expected_score(*, rating: int, opponent_rating: int) -> float:
    """The probability ``rating`` is expected to score against
    ``opponent_rating`` — Elo's logistic curve, 0 to 1. Symmetric by
    construction: swapping the two ratings returns ``1 - expected_score(...)``,
    which is what keeps a pair's rating changes conserved (see
    ``update_rating``)."""
    return 1 / (1 + 10 ** ((opponent_rating - rating) / 400))


def update_rating(*, rating: int, expected: float, actual: float) -> int:
    """The rating after one result. ``actual`` is 1.0 for a win, 0.0 for a
    loss, 0.5 for a draw; ``expected`` is what ``expected_score`` gave this
    side going in. Rounded to the nearest whole point — a ladder lives in
    integers, the same as ``DEFAULT_PLAYER_RATING`` and every scoreboard number
    beside it."""
    return round(rating + K_FACTOR * (actual - expected))


@transaction.atomic
def ensure_ranking(*, player: Player, category: Category) -> Ranking:
    """The player's row in ``category``'s ladder, seeded at
    ``DEFAULT_PLAYER_RATING`` the first time they enter it. The seeding hook:
    called from here rather than from a signal on ``Player`` or ``Category``,
    because which categories a player will ever play is not knowable at
    creation time — the same reasoning as ``apps.players.services
    .ensure_player_for_user``, one layer up."""
    entry, _ = Ranking.objects.get_or_create(
        player=player, category=category, defaults={"rating": DEFAULT_PLAYER_RATING}
    )
    return entry


@transaction.atomic
def update_ratings_for_matchup(*, matchup: Matchup) -> None:
    """Move both players' rating in ``matchup.category`` once, from the result
    now on record.

    A tie — neither ``MatchupPlayer`` marked ``is_winner``
    (``apps.matches.services.complete_matchup``'s "leaves neither side marked a
    winner rather than picking one arbitrarily") — counts as an Elo draw, 0.5
    each, rather than being skipped: two evenly matched players who tie still
    played a game the ladder should reflect.
    """
    sides = list(matchup.players.select_related("player").order_by("joined_at"))
    if len(sides) != PLAYERS_PER_MATCHUP:
        # No opponent ever joined — cancelled before there was a result to
        # score.
        return

    first, second = sides
    first_entry = ensure_ranking(player=first.player, category=matchup.category)
    second_entry = ensure_ranking(player=second.player, category=matchup.category)

    # Locked together, in one stable order, before either rating is read: the
    # exchange is symmetric and computed from the ratings as they stood before
    # this result, so a concurrent result touching one of these two players
    # elsewhere must not make the pair's points stop conserving.
    entry_ids = sorted((first_entry.pk, second_entry.pk))
    locked = {
        row.pk: row
        for row in Ranking.objects.select_for_update().filter(pk__in=entry_ids)
    }
    first_entry, second_entry = locked[first_entry.pk], locked[second_entry.pk]

    if first.is_winner:
        first_actual, second_actual = 1.0, 0.0
    elif second.is_winner:
        first_actual, second_actual = 0.0, 1.0
    else:
        first_actual = second_actual = 0.5

    first_expected = expected_score(
        rating=first_entry.rating, opponent_rating=second_entry.rating
    )
    second_expected = 1 - first_expected

    _apply(entry=first_entry, expected=first_expected, actual=first_actual)
    _apply(entry=second_entry, expected=second_expected, actual=second_actual)

    logger.info(
        f"Ranking updated: {labels.player(first.player)} vs {labels.player(second.player)}",
        category=labels.category(matchup.category),
    )


def _apply(*, entry: Ranking, expected: float, actual: float) -> None:
    entry.rating = update_rating(rating=entry.rating, expected=expected, actual=actual)
    entry.games_played += 1
    if actual == 1.0:
        entry.wins += 1
    elif actual == 0.0:
        entry.losses += 1
    entry.save(update_fields=["rating", "wins", "losses", "games_played", "updated_at"])


def seed_all_players(*, category: Category) -> int:
    """Create a ``Ranking`` row at ``DEFAULT_PLAYER_RATING`` for every player
    missing one in ``category``. Returns how many were created — what
    ``manage.py backfill_rankings`` reports, for players who predate the
    category or predate the seeding hook itself.

    ``ignore_conflicts`` rather than a loop of ``get_or_create``: this runs
    over however many players an install has, and the one thing it needs from
    the database is the uniqueness constraint backstopping a player who
    entered the ladder (via ``ensure_ranking``) between the read and the
    write.
    """
    missing = list(selectors.unrated_players(category=category))
    if not missing:
        return 0
    Ranking.objects.bulk_create(
        [
            Ranking(player=player, category=category, rating=DEFAULT_PLAYER_RATING)
            for player in missing
        ],
        ignore_conflicts=True,
    )
    return len(missing)
