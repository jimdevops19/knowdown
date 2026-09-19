"""A match played *in a room* — the half of the feature that lives in
``apps.matches`` but is only meaningful with a room in front of it.

Kept here rather than in ``apps.matches.tests`` because every assertion is
about what the room decided: the board, the length, and the ladder the result
moves.
"""

from __future__ import annotations

import random

from django.test import TestCase

from apps.core_common.exceptions import ValidationFailed
from apps.matches import services
from apps.matches.tests.factories import stock_category
from apps.players.tests.factories import make_player
from apps.questions.tests.factories import make_category, make_single_answer
from apps.rankings.models import Ranking
from apps.rankings.services.ratings import update_ratings_for_matchup
from apps.rooms.tests.factories import make_room


class MatchupInARoomTests(TestCase):
    def setUp(self):
        self.nba = stock_category(category=make_category(), count=10)
        self.f1 = stock_category(category=make_category(slug="f1", name="F1"), count=10)
        self.one = make_player(email="one@example.com")
        self.two = make_player(email="two@example.com")

    def _room(self, **kwargs):
        kwargs.setdefault("categories", [(self.nba, {})])
        return make_room(**kwargs)

    def test_the_room_decides_the_match_length(self):
        room = self._room(counts=[6])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        self.assertEqual(matchup.question_count, 6)
        self.assertEqual(matchup.questions.count(), 6)

    def test_a_count_the_room_does_not_offer_is_refused(self):
        room = self._room(counts=[4, 5, 6])
        with self.assertRaises(ValidationFailed):
            services.create_matchup(
                room=room, player_one=self.one, player_two=self.two, question_count=7
            )

    def test_the_length_is_drawn_from_the_rooms_own_numbers(self):
        """``[4, 5, 6]`` are lengths the engine's own MATCH_QUESTION_COUNTS
        (3, 5, 7) does not offer — the point of a room stating its own."""
        room = self._room(counts=[4, 6])
        drawn = {
            services.create_matchup(
                room=room,
                player_one=self.one,
                player_two=self.two,
                rng=random.Random(seed),
            ).question_count
            for seed in range(20)
        }
        self.assertTrue(drawn <= {4, 6})

    def test_the_board_comes_from_the_rooms_categories(self):
        room = self._room(counts=[5], categories=[(self.f1, {})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        for question in matchup.questions.all():
            self.assertEqual(
                _category_of(question.question_type, question.question_id), self.f1
            )

    def test_filter_tags_keep_the_board_on_theme(self):
        themed = make_single_answer(slug="finals-only", category=self.nba, level=3)
        themed.tags = {"topic": "finals"}
        themed.save(update_fields=["tags"])
        room = self._room(counts=[1], categories=[(self.nba, {"topic": "finals"})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        self.assertEqual(
            matchup.questions.get().question_id, str(themed.id)
        )

    def test_a_matchup_is_filed_under_the_rooms_first_category(self):
        """Every matchup carries a category. A mixed room still has one — the
        first it lists — so its matches are filed somewhere sensible, even
        though nothing is scored against it (see the ranked tests below)."""
        room = self._room(counts=[3], categories=[(self.f1, {}), (self.nba, {})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        self.assertEqual(matchup.category, self.f1)
        self.assertEqual(matchup.room, room)

    def test_a_single_category_room_is_ranked(self):
        """Every question asked belongs to the category the result moves, so
        the rating means what it says."""
        room = self._room(counts=[3], categories=[(self.nba, {})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        self.assertTrue(matchup.is_ranked)

    def test_a_room_mixing_categories_is_not_ranked(self):
        """The rule this whole distinction exists for: a result can only move
        one ladder, so a room drawing from two sports would credit the first
        for questions that came from the second. It is played unrated
        instead."""
        room = self._room(counts=[3], categories=[(self.nba, {}), (self.f1, {})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        self.assertFalse(matchup.is_ranked)

    def test_an_unranked_room_result_moves_nobody(self):
        """End of the pipeline, not just the flag: the rating service is the
        one reader of ``is_ranked``, and a mixed room must leave the ladder
        exactly as it found it — no row seeded, no number changed."""
        room = self._room(counts=[3], categories=[(self.nba, {}), (self.f1, {})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        matchup.players.filter(player=self.one).update(is_winner=True)

        update_ratings_for_matchup(matchup=matchup)

        self.assertFalse(Ranking.objects.exists())

    def test_filter_tags_do_not_make_a_room_unranked(self):
        """Narrowing one category is still one category — the themed rooms
        that ship (Ring Chasing, The 2000s, Hardware) are all of this shape and
        must keep counting."""
        themed = make_single_answer(slug="ranked-finals", category=self.nba, level=3)
        themed.tags = {"topic": "finals"}
        themed.save(update_fields=["tags"])
        room = self._room(counts=[1], categories=[(self.nba, {"topic": "finals"})])
        matchup = services.create_matchup(
            room=room, player_one=self.one, player_two=self.two
        )
        self.assertTrue(matchup.is_ranked)

    def test_a_room_too_thin_to_fill_its_own_match_refuses(self):
        sparse = make_category(slug="sparse", name="Sparse")
        make_single_answer(slug="only-one", category=sparse, level=3)
        room = self._room(counts=[5], categories=[(sparse, {})])
        with self.assertRaises(ValidationFailed) as caught:
            services.create_matchup(
                room=room, player_one=self.one, player_two=self.two
            )
        self.assertEqual(caught.exception.code, "not_enough_questions")

    def test_a_category_only_matchup_still_works(self):
        """Rooms are additive: the rehearsal fixtures, bot seeding and every
        older caller hold a category and no room."""
        matchup = services.create_matchup(
            category=self.nba, player_one=self.one, player_two=self.two
        )
        self.assertIsNone(matchup.room)
        self.assertEqual(matchup.category, self.nba)

    def test_a_matchup_needs_a_room_or_a_category(self):
        with self.assertRaises(ValidationFailed):
            services.create_matchup(player_one=self.one, player_two=self.two)

    def test_a_room_with_no_categories_cannot_be_played(self):
        room = make_room(slug="empty", categories=[])
        with self.assertRaises(ValidationFailed):
            services.create_matchup(
                room=room, player_one=self.one, player_two=self.two
            )


class TiebreakInARoomTests(TestCase):
    """Sudden death must stay inside the room's own theme."""

    def setUp(self):
        self.nba = make_category()
        self.themed = [
            make_single_answer(slug=f"finals-{i}", category=self.nba, level=3)
            for i in range(4)
        ]
        for question in self.themed:
            question.tags = {"topic": "finals"}
            question.save(update_fields=["tags"])
        # Off-theme questions in the same category — the pool a category-wide
        # tie-breaker would (wrongly) reach into.
        for i in range(10):
            make_single_answer(slug=f"draft-{i}", category=self.nba, level=3)
        self.room = make_room(
            slug="finals-room", counts=[3], categories=[(self.nba, {"topic": "finals"})]
        )

    def test_a_tiebreaker_is_drawn_from_the_room_not_the_category(self):
        matchup = services.create_matchup(
            room=self.room,
            player_one=make_player(email="one@example.com"),
            player_two=make_player(email="two@example.com"),
        )
        extra = services.add_tiebreaker_question(matchup=matchup)
        self.assertIsNotNone(extra)
        self.assertIn(
            extra.question_id, {str(question.id) for question in self.themed}
        )

    def test_no_tiebreaker_when_the_room_is_exhausted(self):
        """Better a match settled on answer time than one that repeats a
        question either player saw a minute ago."""
        room = make_room(
            slug="tiny", counts=[3], categories=[(self.nba, {"topic": "finals"})]
        )
        matchup = services.create_matchup(
            room=room,
            player_one=make_player(email="three@example.com"),
            player_two=make_player(email="four@example.com"),
        )
        # Three of the four themed questions are on the board; retire whichever
        # one is not, and the room has nothing left it has not already asked.
        played = set(matchup.questions.values_list("question_id", flat=True))
        for question in self.themed:
            if str(question.id) not in played:
                question.is_active = False
                question.save(update_fields=["is_active"])
        self.assertIsNone(services.add_tiebreaker_question(matchup=matchup))


def _category_of(question_type: str, question_id: str):
    from apps.questions.selectors import QuestionRef, get_question

    return get_question(ref=QuestionRef(question_type, question_id)).category
