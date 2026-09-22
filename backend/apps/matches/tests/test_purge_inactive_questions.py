"""``manage.py purge_inactive_questions`` — the one command that really deletes
a question.

Every other path in the platform deactivates instead (``sync_questions``), so
what these tests are about is the *cost* of the exception: the question row is
gone for real, the match rows that pointed at it are gone with it — no dangling
``(question_type, question_id)`` pair for ``get_question`` to raise on — and
nothing else about a played match moves.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.matches.models import MatchupQuestion, PlayerAnswer
from apps.matches.tests.factories import make_matchup
from apps.questions.models import QuestionType, SingleAnswerImageQuestion
from apps.questions.tests.factories import make_category, make_image_answer
from apps.questions.tests.factories import make_single_answer


def _run(*args, stdin_is_a_terminal: bool = True, answers=()) -> str:
    """Run the command, answering its prompts with ``answers``.

    ``isatty`` is patched because a test has no terminal, and the command
    refuses one-by-one approval without one — that refusal is its own test
    below.
    """
    out = StringIO()
    with (
        mock.patch("sys.stdin.isatty", return_value=stdin_is_a_terminal),
        mock.patch("builtins.input", side_effect=list(answers)),
    ):
        call_command("purge_inactive_questions", *args, stdout=out, stderr=out)
    return out.getvalue()


class PurgeInactiveQuestionsTests(TestCase):
    def setUp(self):
        self.category = make_category(slug="nba")
        self.doomed = make_image_answer(
            slug="doomed", category=self.category, level=1
        )
        self.doomed.is_active = False
        self.doomed.save(update_fields=["is_active"])
        self.kept = make_image_answer(slug="kept", category=self.category, level=1)

    def _play_it(self) -> tuple:
        """Put ``self.doomed`` into a real matchup, answered by both sides."""
        matchup = make_matchup(category=self.category)
        row = MatchupQuestion.objects.create(
            matchup=matchup,
            question_id=str(self.doomed.id),
            question_type=QuestionType.IMAGE_ANSWER,
            order=matchup.question_count + 1,
        )
        for side in matchup.players.all():
            PlayerAnswer.objects.create(
                matchup_question=row,
                player=side.player,
                answer={"option_id": 1},
                is_correct=True,
                score=1.0,
                points=100,
                response_time_ms=1200,
            )
        return matchup, row

    def test_dry_run_is_the_default_and_writes_nothing(self):
        matchup, row = self._play_it()

        output = _run()

        self.assertIn("doomed", output)
        self.assertIn("1 match question(s)", output)
        self.assertIn("Dry run", output)
        self.assertTrue(SingleAnswerImageQuestion.all_objects.filter(id=self.doomed.id).exists())
        self.assertTrue(MatchupQuestion.objects.filter(id=row.id).exists())

    def test_yes_purges_the_question_and_its_match_rows(self):
        matchup, row = self._play_it()
        scores_before = sorted(matchup.players.values_list("score", flat=True))

        output = _run("--no-dry-run", "--yes")

        self.assertIn("Purged 1 question(s)", output)
        self.assertFalse(
            SingleAnswerImageQuestion.all_objects.filter(id=self.doomed.id).exists()
        )
        # The debris, gone with it — a `MatchupQuestion` left behind would be a
        # box score that raises `NotFound` when somebody opens it.
        self.assertFalse(MatchupQuestion.objects.filter(id=row.id).exists())
        self.assertEqual(PlayerAnswer.objects.filter(matchup_question_id=row.id).count(), 0)
        # The match itself stands, at the score it was played to.
        matchup.refresh_from_db()
        self.assertEqual(
            sorted(matchup.players.values_list("score", flat=True)), scores_before
        )
        # And an active question of the same type is untouched.
        self.assertTrue(SingleAnswerImageQuestion.objects.filter(id=self.kept.id).exists())

    def test_the_question_goes_for_real_not_soft_deleted(self):
        """A soft delete would leave the slug taken and the next sync reviving
        it — the reason this command exists at all."""
        _run("--no-dry-run", "--yes")

        self.assertFalse(
            SingleAnswerImageQuestion.all_objects.filter(slug="doomed").exists()
        )

    def test_one_by_one_approval_keeps_what_was_refused(self):
        second = make_image_answer(slug="doomed-two", category=self.category)
        second.is_active = False
        second.save(update_fields=["is_active"])

        output = _run("--no-dry-run", answers=["n", "y"])

        self.assertIn("kept doomed", output)
        self.assertTrue(SingleAnswerImageQuestion.all_objects.filter(slug="doomed").exists())
        self.assertFalse(
            SingleAnswerImageQuestion.all_objects.filter(slug="doomed-two").exists()
        )

    def test_all_approves_the_rest_without_asking_again(self):
        second = make_image_answer(slug="doomed-two", category=self.category)
        second.is_active = False
        second.save(update_fields=["is_active"])

        # One answer for two questions: the second is never asked about.
        _run("--no-dry-run", answers=["a"])

        self.assertEqual(SingleAnswerImageQuestion.all_objects.filter(is_active=False).count(), 0)

    def test_quit_stops_before_the_question_it_was_asked_about(self):
        second = make_image_answer(slug="doomed-two", category=self.category)
        second.is_active = False
        second.save(update_fields=["is_active"])

        output = _run("--no-dry-run", answers=["y", "q"])

        self.assertIn("Stopped", output)
        self.assertFalse(SingleAnswerImageQuestion.all_objects.filter(slug="doomed").exists())
        self.assertTrue(SingleAnswerImageQuestion.all_objects.filter(slug="doomed-two").exists())

    def test_refuses_one_by_one_approval_with_no_terminal_to_ask_at(self):
        with self.assertRaises(CommandError):
            _run("--no-dry-run", stdin_is_a_terminal=False)

        self.assertTrue(SingleAnswerImageQuestion.all_objects.filter(slug="doomed").exists())

    def test_a_soft_deleted_row_counts_as_inactive(self):
        """It is unplayable and it is still holding its slug in the unique
        index, which is what somebody running this is trying to free."""
        hidden = make_image_answer(slug="hidden", category=self.category)
        hidden.delete()

        _run("--no-dry-run", "--yes", "--slug", "hidden")

        self.assertFalse(SingleAnswerImageQuestion.all_objects.filter(slug="hidden").exists())

    def test_filters_scope_what_is_found(self):
        other_category = make_category(slug="nfl", name="NFL")
        other_type = make_single_answer(slug="text-one", category=other_category)
        other_type.is_active = False
        other_type.save(update_fields=["is_active"])

        by_type = _run("--type", QuestionType.IMAGE_ANSWER)
        self.assertIn("doomed", by_type)
        self.assertNotIn("text-one", by_type)

        by_category = _run("--category", "nfl")
        self.assertIn("text-one", by_category)
        self.assertNotIn("doomed", by_category)

        by_slug = _run("--slug", "doomed")
        self.assertIn("doomed", by_slug)
        self.assertNotIn("text-one", by_slug)

    def test_says_so_when_nothing_matches(self):
        output = _run("--slug", "no-such-question")

        self.assertIn("Nothing to purge", output)
