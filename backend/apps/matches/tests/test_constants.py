"""The clock a question gets, and the two places that have to agree about it.

Each question model states its own ``DEFAULT_TIME_LIMIT_SECONDS`` (how long a
question of that shape stays open when its author names no number), and
``apps.matches.constants.time_limit_ms_for`` is the one place the tiers —
authored override, then the type's default — are resolved. This file holds the
seam honest in both directions: that every registered type is actually reachable
through the function, and that the gradual-hints default is still a clock the
loader will accept a default hint schedule inside of.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.matches.constants import (
    FALLBACK_QUESTION_TIME_LIMIT_SECONDS,
    time_limit_ms_for,
)
from apps.questions.constants import HINT_ANSWER_WINDOW_SECONDS
from apps.questions.models import (
    DEFAULT_HINT_INTERVAL_SECONDS,
    QUESTION_MODELS,
    MAX_HINTS,
    BaseQuestion,
    GradualHintsQuestion,
    QuestionType,
)


class DefaultTimeLimitTests(SimpleTestCase):
    def test_every_type_resolves_to_its_own_models_default(self) -> None:
        """The registry is the list of types that exist, so a type that is
        added to it and nowhere else must still get the clock its class names —
        never a number this app keeps a second copy of."""
        for question_type, model in QUESTION_MODELS.items():
            with self.subTest(question_type=question_type):
                self.assertEqual(
                    time_limit_ms_for(question_type=question_type),
                    model.DEFAULT_TIME_LIMIT_SECONDS * 1000,
                )

    def test_a_type_that_says_nothing_gets_the_ordinary_clock(self) -> None:
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.SINGLE_ANSWER),
            FALLBACK_QUESTION_TIME_LIMIT_SECONDS * 1000,
        )
        self.assertEqual(
            FALLBACK_QUESTION_TIME_LIMIT_SECONDS, BaseQuestion.DEFAULT_TIME_LIMIT_SECONDS
        )

    def test_an_authored_override_outranks_every_default(self) -> None:
        """Including on a type whose own default is the longest one there is —
        the override is the most specific tier, not merely a louder vote."""
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.GRADUAL_HINTS, override_seconds=5),
            5_000,
        )
        self.assertEqual(
            time_limit_ms_for(question_type=QuestionType.SINGLE_ANSWER, override_seconds=5),
            5_000,
        )


class GradualHintsClockTests(SimpleTestCase):
    def test_a_full_default_schedule_fits_the_default_clock(self) -> None:
        """The default question — five clues at the default spacing — must load
        without its author having to think about the clock at all.

        The loader would refuse it otherwise (``schemas.GradualHintsSpec``), and
        "every question of this type needs a ``time_limit_seconds``" is a
        default that is not one.
        """
        last_hint_at = (MAX_HINTS - 1) * DEFAULT_HINT_INTERVAL_SECONDS
        self.assertGreaterEqual(
            GradualHintsQuestion.DEFAULT_TIME_LIMIT_SECONDS - last_hint_at,
            HINT_ANSWER_WINDOW_SECONDS,
        )
