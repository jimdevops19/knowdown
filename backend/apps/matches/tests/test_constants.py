"""The numbers, and the two places that have to agree about one of them.

``apps.matches.constants`` owns how long a question stays open.
``apps.questions.constants`` holds a *copy* of the gradual-hints clock, because
the loader has to refuse a hint schedule that would not fit inside it and
importing the match engine into the question schemas would invert every other
dependency in the platform — the arrangement
``apps.questions.constants.LONGEST_MATCH_QUESTION_COUNT`` already describes for
the other direction.

A copy is only honest if something checks it, which is this file. Without it the
drift is silent and bad in both directions: a copy that grew would accept
questions whose last clue the engine then cuts off, and a player would find out
with the clock running; a copy that shrank would refuse questions the engine
would happily have run.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.matches.constants import (
    FALLBACK_QUESTION_TIME_LIMITS_MS,
    time_limit_ms_for,
)
from apps.questions.constants import (
    GRADUAL_HINTS_FALLBACK_CLOCK_SECONDS,
    HINT_ANSWER_WINDOW_SECONDS,
)
from apps.questions.models import (
    DEFAULT_HINT_INTERVAL_SECONDS,
    MAX_HINTS,
    QuestionType,
)


class GradualHintsClockTests(SimpleTestCase):
    def test_the_questions_apps_copy_of_the_clock_is_this_ones(self) -> None:
        self.assertEqual(
            GRADUAL_HINTS_FALLBACK_CLOCK_SECONDS * 1000,
            FALLBACK_QUESTION_TIME_LIMITS_MS[QuestionType.GRADUAL_HINTS],
        )

    def test_the_fallback_is_what_a_question_without_an_override_gets(self) -> None:
        """The copy is only worth checking if it is the number actually used —
        this asserts the tier, not just the constant."""
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.GRADUAL_HINTS),
            GRADUAL_HINTS_FALLBACK_CLOCK_SECONDS * 1000,
        )

    def test_a_full_default_schedule_fits_the_fallback(self) -> None:
        """The default question — five clues at the default spacing — must load
        without its author having to think about the clock at all.

        The loader would refuse it otherwise (``schemas.GradualHintsSpec``), and
        "every question of this type needs a ``time_limit_seconds``" is a
        default that is not one.
        """
        last_hint_at = (MAX_HINTS - 1) * DEFAULT_HINT_INTERVAL_SECONDS
        self.assertGreaterEqual(
            GRADUAL_HINTS_FALLBACK_CLOCK_SECONDS - last_hint_at,
            HINT_ANSWER_WINDOW_SECONDS,
        )
