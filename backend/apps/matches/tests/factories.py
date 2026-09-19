"""Match fixtures: a stocked category and two players, built through the
services the way ``accounts.tests.factories``/``players.tests.factories`` do."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from apps.categories.models import Category
from apps.matches import constants, services
from apps.matches.models import Matchup
from apps.players.models import Player
from apps.players.tests.factories import make_player
from apps.questions.tests.factories import make_category, make_single_answer


@contextmanager
def default_clock(seconds: int) -> Iterator[None]:
    """Run the block with the fallback question clock set to ``seconds``.

    A question built straight through the ORM authors no ``time_limit_seconds``
    and belongs to no resource file, so the clock it gets is
    ``constants.FALLBACK_QUESTION_TIME_LIMIT_MS`` — the one tier left once the
    two authored ones are absent (``constants.time_limit_ms_for``). A test that
    needs a question to close *now* says so here, and both the watchdog in
    ``consumers`` and the deadline in ``services`` see it, because both read the
    constant through the same function at call time.
    """
    with mock.patch.object(constants, "FALLBACK_QUESTION_TIME_LIMIT_MS", seconds * 1000):
        yield


def stock_category(*, category: Category | None = None, count: int = 10) -> Category:
    """A category with enough single-answer questions to draw any of
    ``MATCH_QUESTION_COUNTS`` from. Option order 1 is always the correct one
    (``make_single_answer``'s default), which is what a test answers to win a
    question outright."""
    category = category or make_category()
    stamp = uuid.uuid4().hex[:8]
    for n in range(count):
        make_single_answer(slug=f"q-{stamp}-{n}", category=category, level=3)
    return category


def make_matchup(
    *,
    category: Category | None = None,
    player_one: Player | None = None,
    player_two: Player | None = None,
    question_count: int | None = None,
) -> Matchup:
    category = stock_category(category=category)
    stamp = uuid.uuid4().hex[:8]
    player_one = player_one or make_player(email=f"one-{stamp}@example.com")
    player_two = player_two or make_player(email=f"two-{stamp}@example.com")
    return services.create_matchup(
        category=category,
        player_one=player_one,
        player_two=player_two,
        question_count=question_count,
    )
