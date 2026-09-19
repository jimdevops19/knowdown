"""The pool a room implies, and the draw over it."""

from __future__ import annotations

import random

from django.test import TestCase

from apps.core_common.exceptions import NotFound, ValidationFailed
from apps.questions.tests.factories import make_category, make_single_answer
from apps.rooms.selectors import (
    active_rooms,
    get_room_by_slug,
    room_pool_size,
    room_question_pool,
    select_room_questions,
)
from apps.rooms.tests.factories import make_room


class RoomPoolTests(TestCase):
    def setUp(self):
        self.nba = make_category()
        self.f1 = make_category(slug="f1", name="F1")
        self.finals = [
            make_single_answer(
                slug=f"finals-{i}", category=self.nba, level=5
            )
            for i in range(3)
        ]
        for question in self.finals:
            question.tags = {"topic": "finals", "era": "2010s"}
            question.save(update_fields=["tags"])
        self.draft = make_single_answer(slug="draft-1", category=self.nba, level=5)
        self.draft.tags = {"topic": "draft"}
        self.draft.save(update_fields=["tags"])
        self.race = make_single_answer(slug="race-1", category=self.f1, level=5)

    def test_an_unfiltered_room_offers_its_whole_category(self):
        room = make_room(categories=[(self.nba, {})])
        self.assertEqual(len(room_question_pool(room=room)), 4)

    def test_filter_tags_narrow_the_category(self):
        room = make_room(categories=[(self.nba, {"topic": "finals"})])
        pool = room_question_pool(room=room)
        self.assertEqual(
            {ref.question_id for ref in pool},
            {str(question.id) for question in self.finals},
        )

    def test_a_question_carrying_extra_facets_still_matches(self):
        """Tags match on containment — that is what makes a themed room
        buildable out of the catalog that already exists."""
        room = make_room(categories=[(self.nba, {"era": "2010s"})])
        self.assertEqual(len(room_question_pool(room=room)), 3)

    def test_a_room_mixes_its_categories(self):
        room = make_room(
            categories=[(self.nba, {"topic": "finals"}), (self.f1, {})]
        )
        self.assertEqual(len(room_question_pool(room=room)), 4)

    def test_an_inactive_category_is_skipped_not_refused(self):
        """One sport out of season must not take a mixed room offline."""
        self.f1.is_active = False
        self.f1.save(update_fields=["is_active"])
        room = make_room(categories=[(self.nba, {"topic": "draft"}), (self.f1, {})])
        self.assertEqual(len(room_question_pool(room=room)), 1)

    def test_an_inactive_question_is_never_offered(self):
        self.draft.is_active = False
        self.draft.save(update_fields=["is_active"])
        room = make_room(categories=[(self.nba, {})])
        self.assertEqual(len(room_question_pool(room=room)), 3)

    def test_pool_size_agrees_with_the_pool(self):
        room = make_room(categories=[(self.nba, {"topic": "finals"}), (self.f1, {})])
        self.assertEqual(room_pool_size(room=room), len(room_question_pool(room=room)))

    def test_the_primary_category_is_the_first_one_listed(self):
        room = make_room(categories=[(self.f1, {}), (self.nba, {})])
        self.assertEqual(room.primary_category, self.f1)


class SelectRoomQuestionsTests(TestCase):
    def setUp(self):
        self.nba = make_category()
        self.questions = [
            make_single_answer(slug=f"q-{i}", category=self.nba, level=5)
            for i in range(5)
        ]
        self.room = make_room(counts=[3], categories=[(self.nba, {})])

    def test_draws_the_count_asked_for_without_repeats(self):
        refs = select_room_questions(room=self.room, count=3)
        self.assertEqual(len(refs), 3)
        self.assertEqual(len({ref.as_tuple() for ref in refs}, ), 3)

    def test_the_draw_is_pinnable(self):
        one = select_room_questions(room=self.room, count=3, rng=random.Random(7))
        two = select_room_questions(room=self.room, count=3, rng=random.Random(7))
        self.assertEqual(one, two)

    def test_refuses_rather_than_playing_a_shorter_match(self):
        with self.assertRaises(ValidationFailed) as caught:
            select_room_questions(room=self.room, count=99)
        self.assertEqual(caught.exception.code, "not_enough_questions")

    def test_refuses_a_count_below_one(self):
        with self.assertRaises(ValidationFailed):
            select_room_questions(room=self.room, count=0)

    def test_exclude_takes_refs_out_of_the_pool(self):
        """What a tie-breaker needs: never a question already played here."""
        played = {(q.question_type, str(q.id)) for q in self.questions[:4]}
        refs = select_room_questions(room=self.room, count=1, exclude=played)
        self.assertEqual(refs[0].question_id, str(self.questions[4].id))

    def test_a_choose_strategy_decides_which_refs_come_out(self):
        def first_n(*, pool, count, rng):
            return sorted(pool, key=lambda ref: ref.question_id)[:count]

        refs = select_room_questions(room=self.room, count=2, choose=first_n)
        self.assertEqual(refs, first_n(pool=room_question_pool(room=self.room), count=2, rng=None))

    def test_a_room_whose_filters_match_nothing_refuses(self):
        empty = make_room(slug="empty-room", categories=[(self.nba, {"era": "1890s"})])
        with self.assertRaises(ValidationFailed):
            select_room_questions(room=empty, count=1)


class RoomLookupTests(TestCase):
    def setUp(self):
        self.nba = make_category()

    def test_active_rooms_excludes_the_inactive(self):
        make_room(slug="live", categories=[(self.nba, {})])
        make_room(slug="parked", is_active=False, categories=[(self.nba, {})])
        self.assertEqual(
            list(active_rooms().values_list("slug", flat=True)), ["live"]
        )

    def test_rooms_come_back_in_their_authored_order(self):
        make_room(slug="second", display_order=2, categories=[(self.nba, {})])
        make_room(slug="first", display_order=1, categories=[(self.nba, {})])
        self.assertEqual(
            list(active_rooms().values_list("slug", flat=True)), ["first", "second"]
        )

    def test_get_room_by_slug_refuses_an_inactive_room_by_default(self):
        make_room(slug="parked", is_active=False, categories=[(self.nba, {})])
        with self.assertRaises(NotFound):
            get_room_by_slug(slug="parked")
        self.assertEqual(
            get_room_by_slug(slug="parked", include_inactive=True).slug, "parked"
        )

    def test_get_room_by_slug_refuses_an_unknown_slug(self):
        with self.assertRaises(NotFound):
            get_room_by_slug(slug="nope")
