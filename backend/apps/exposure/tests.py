"""The dedup-and-bias story: never a repeat for either player while an unseen
question remains, and a counted, alertable trail once one is forced."""

from __future__ import annotations

from django.test import TestCase

from apps.exposure.models import QuestionExposure
from apps.exposure.selectors import pick_least_exposed, repeated_exposures
from apps.exposure.services import record_exposures
from apps.players.tests.factories import make_player
from apps.questions.selectors import QuestionRef


def _ref(n: int) -> QuestionRef:
    return QuestionRef("single-answer", f"q-{n}")


class RecordExposuresTests(TestCase):
    def test_a_first_sighting_starts_at_one(self) -> None:
        player = make_player()
        record_exposures(player_ids=[player.id], refs=[_ref(1)])

        row = QuestionExposure.objects.get(player=player, question_id="q-1")
        self.assertEqual(row.times_seen, 1)

    def test_a_repeat_sighting_bumps_the_same_row_rather_than_inserting_one(self) -> None:
        player = make_player()
        record_exposures(player_ids=[player.id], refs=[_ref(1)])
        record_exposures(player_ids=[player.id], refs=[_ref(1)])

        self.assertEqual(
            QuestionExposure.objects.filter(player=player, question_id="q-1").count(), 1
        )
        row = QuestionExposure.objects.get(player=player, question_id="q-1")
        self.assertEqual(row.times_seen, 2)

    def test_one_call_records_both_players_of_a_matchup(self) -> None:
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        record_exposures(player_ids=[alice.id, bob.id], refs=[_ref(1), _ref(2)])

        self.assertEqual(QuestionExposure.objects.filter(player=alice).count(), 2)
        self.assertEqual(QuestionExposure.objects.filter(player=bob).count(), 2)


class PickLeastExposedTests(TestCase):
    def test_an_unseen_question_always_outranks_a_seen_one(self) -> None:
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        pool = [_ref(1), _ref(2), _ref(3)]
        record_exposures(player_ids=[alice.id, bob.id], refs=[_ref(1)])

        chosen = pick_least_exposed(player_ids=[alice.id, bob.id], pool=pool, count=2)

        self.assertNotIn(_ref(1), chosen)
        self.assertEqual(set(chosen), {_ref(2), _ref(3)})

    def test_either_players_prior_exposure_is_enough_to_rank_a_question_down(self) -> None:
        """The worse-case side decides — a question already shown to just one
        of the two must not be handed back to that side because the other
        has never seen it."""
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        pool = [_ref(1), _ref(2)]
        record_exposures(player_ids=[alice.id], refs=[_ref(1)])  # bob has not seen it

        chosen = pick_least_exposed(player_ids=[alice.id, bob.id], pool=pool, count=1)

        self.assertEqual(chosen, [_ref(2)])

    def test_only_once_every_fresh_question_is_gone_does_a_repeat_surface(self) -> None:
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        pool = [_ref(1), _ref(2)]
        record_exposures(player_ids=[alice.id, bob.id], refs=pool)  # both seen once

        chosen = pick_least_exposed(player_ids=[alice.id, bob.id], pool=pool, count=2)

        self.assertEqual(set(chosen), {_ref(1), _ref(2)})


class RepeatedExposuresTests(TestCase):
    def test_finds_only_pairs_seen_more_than_once(self) -> None:
        player = make_player()
        record_exposures(player_ids=[player.id], refs=[_ref(1), _ref(2)])
        record_exposures(player_ids=[player.id], refs=[_ref(1)])  # q-1 now seen twice

        rows = repeated_exposures()

        self.assertEqual([row.question_id for row in rows], ["q-1"])
