"""The clock a question gets, and the two places that have to agree about it.

A clock is resolved in one function — ``apps.matches.constants
.time_limit_ms_for`` — from one stored number, the question's own
``time_limit_seconds``. Everything above that tier happens at *load* time: a
resource file states the clock for the whole answer shape it holds
(``apps.questions.schemas.QuestionFileSpec``) and the loader writes it onto
every row that named none of its own, so the engine reads one resolved value
rather than re-deciding the tiers per caller.

This file holds the last tier honest: a row with nothing on it plays at the
ordinary clock, and that clock is the questions domain's own number rather
than a second copy of it. What each answer shape is actually worth is a
resource file's business now, and ``apps.questions.tests.test_sync`` is where
a file's clock is proven to reach its rows.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.matches.constants import (
    FALLBACK_QUESTION_TIME_LIMIT_SECONDS,
    PRE_QUESTION_INFO_MS,
    QUESTION_READ_DELAY_MS,
    read_delay_ms_for,
    time_limit_ms_for,
)
from apps.questions.constants import DEFAULT_TIME_LIMIT_SECONDS


class TimeLimitTests(SimpleTestCase):
    def test_a_question_that_names_no_clock_gets_the_ordinary_one(self) -> None:
        self.assertEqual(
            time_limit_ms_for(), FALLBACK_QUESTION_TIME_LIMIT_SECONDS * 1000
        )
        self.assertEqual(time_limit_ms_for(override_seconds=None), 10_000)

    def test_the_engine_s_fallback_is_the_catalog_s_default(self) -> None:
        """An alias, not a second ten: the loader validates hint schedules
        against the questions-domain number, and the engine counts down from
        this one. Two copies could drift, and the drift would be a question
        that loads and then closes early."""
        self.assertEqual(
            FALLBACK_QUESTION_TIME_LIMIT_SECONDS, DEFAULT_TIME_LIMIT_SECONDS
        )

    def test_a_row_s_own_clock_outranks_the_fallback(self) -> None:
        """Whatever put it there — an entry that asked for it, or the file its
        whole answer shape is authored in, which the loader copies down."""
        self.assertEqual(time_limit_ms_for(override_seconds=5), 5_000)
        self.assertEqual(time_limit_ms_for(override_seconds=60), 60_000)


class ReadDelayTests(SimpleTestCase):
    """How long a question sits before its clock starts — and the one thing
    that lengthens it.

    A question that states its task first (``pre_question_info``) is shown that
    line alone before it is dealt, and the beat is *added* to the reading one
    rather than taken out of it: a player who spent the read delay working out
    what an ordering board is has not read the question, and would meet the
    clock having done half the job the delay exists for.
    """

    def test_an_ordinary_question_gets_the_ordinary_delay(self) -> None:
        self.assertEqual(read_delay_ms_for(), QUESTION_READ_DELAY_MS)
        self.assertEqual(read_delay_ms_for(pre_question_info=""), QUESTION_READ_DELAY_MS)

    def test_a_question_that_states_its_task_is_given_the_beat_for_it(self) -> None:
        self.assertEqual(
            read_delay_ms_for(pre_question_info="Click to order from earliest to latest"),
            QUESTION_READ_DELAY_MS + PRE_QUESTION_INFO_MS,
        )

    def test_the_task_beat_is_added_and_never_taken_out(self) -> None:
        """Stated as its own test because it is the property the whole design
        rests on: the reading beat a question with a task screen gets is the
        same one every other question gets, not a share of it."""
        self.assertGreater(read_delay_ms_for(pre_question_info="Do the thing"), read_delay_ms_for())
