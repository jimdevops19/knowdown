"""Step 17: a rating per player, per category, moved once per matchup.

Two layers: the pure Elo arithmetic (no database), and the pipeline that
persists it — driven both directly (to control the inputs precisely) and
through ``apps.matches.services.complete_matchup``/``abandon_matchup``, which
is the actual integration point (``backend/CLAUDE.md``'s "Done when").
"""

from __future__ import annotations

from django.test import TestCase

from apps.matches import services as match_services
from apps.matches.constants import DEFAULT_PLAYER_RATING
from apps.matches.models import MatchupPlayer
from apps.matches.tests.factories import make_matchup
from apps.players.models import Player
from apps.players.tests.factories import make_player
from apps.rankings import selectors
from apps.rankings.constants import K_FACTOR
from apps.rankings.models import Ranking
from apps.rankings.services import ratings


class ArithmeticTests(TestCase):
    """No database involved — every rule here is checkable on paper."""

    def test_expected_score_is_even_between_equal_ratings(self):
        self.assertAlmostEqual(
            ratings.expected_score(rating=1200, opponent_rating=1200), 0.5
        )

    def test_expected_score_is_symmetric(self):
        a = ratings.expected_score(rating=1400, opponent_rating=1100)
        b = ratings.expected_score(rating=1100, opponent_rating=1400)
        self.assertAlmostEqual(a + b, 1.0)

    def test_a_win_raises_the_rating_a_loss_lowers_it(self):
        expected = ratings.expected_score(rating=1200, opponent_rating=1200)
        winner = ratings.update_rating(rating=1200, expected=expected, actual=1.0)
        loser = ratings.update_rating(rating=1200, expected=expected, actual=0.0)
        self.assertGreater(winner, 1200)
        self.assertLess(loser, 1200)
        # Between two equally-rated players the exchange is exactly K/2 each
        # way — the textbook case, and worth pinning to the constant.
        self.assertEqual(winner - 1200, K_FACTOR // 2)
        self.assertEqual(1200 - loser, K_FACTOR // 2)

    def test_a_draw_between_equal_ratings_moves_nothing(self):
        expected = ratings.expected_score(rating=1200, opponent_rating=1200)
        self.assertEqual(
            ratings.update_rating(rating=1200, expected=expected, actual=0.5), 1200
        )

    def test_beating_a_higher_rated_opponent_pays_more_than_beating_a_lower_one(self):
        expected_vs_stronger = ratings.expected_score(rating=1200, opponent_rating=1400)
        expected_vs_weaker = ratings.expected_score(rating=1200, opponent_rating=1000)
        upset_gain = ratings.update_rating(
            rating=1200, expected=expected_vs_stronger, actual=1.0
        ) - 1200
        expected_gain = ratings.update_rating(
            rating=1200, expected=expected_vs_weaker, actual=1.0
        ) - 1200
        self.assertGreater(upset_gain, expected_gain)


class EnsureRankingTests(TestCase):
    def test_seeds_a_new_player_at_the_default_rating(self):
        player = make_player(email="rookie@example.com")
        category = make_matchup().category  # a stocked category, cheaply
        entry = ratings.ensure_ranking(player=player, category=category)
        self.assertEqual(entry.rating, DEFAULT_PLAYER_RATING)
        self.assertEqual(entry.games_played, 0)

    def test_is_idempotent(self):
        player = make_player(email="again@example.com")
        category = make_matchup().category
        first = ratings.ensure_ranking(player=player, category=category)
        Ranking.objects.filter(pk=first.pk).update(rating=1500)
        second = ratings.ensure_ranking(player=player, category=category)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.rating, 1500)  # not reset to the default


def _play_to_completion(*, winner_correct: bool, question_count: int = 3):
    """A matchup driven to ``COMPLETED`` through the real service calls —
    the path ``complete_matchup`` actually runs in production. Alice always
    answers correctly; Bob does or doesn't, so the winner is deterministic
    without pinning the question RNG."""
    from apps.questions.selectors import QuestionRef, get_question

    matchup = make_matchup(question_count=question_count)
    alice, bob = (side.player for side in matchup.players.all())
    match_services.start_matchup(matchup=matchup)

    for order in range(1, question_count + 1):
        matchup.refresh_from_db()
        row = matchup.questions.get(order=order)
        concrete = get_question(ref=QuestionRef(row.question_type, row.question_id))
        correct_id = concrete.options.get(is_correct=True).id
        wrong_id = concrete.options.filter(is_correct=False).first().id
        match_services.submit_answer(
            matchup=matchup, player=alice, order=order,
            payload={"type": "single-answer", "option_id": correct_id},
        )
        match_services.submit_answer(
            matchup=matchup, player=bob, order=order,
            payload={
                "type": "single-answer",
                "option_id": correct_id if not winner_correct else wrong_id,
            },
        )
    matchup.refresh_from_db()
    return matchup, alice, bob


class UpdateRatingsForMatchupTests(TestCase):
    def test_complete_matchup_moves_both_sides_once(self):
        matchup, alice, bob = _play_to_completion(winner_correct=True)

        alice_entry = selectors.get_ranking(player=alice, category=matchup.category)
        bob_entry = selectors.get_ranking(player=bob, category=matchup.category)

        self.assertGreater(alice_entry.rating, DEFAULT_PLAYER_RATING)
        self.assertLess(bob_entry.rating, DEFAULT_PLAYER_RATING)
        self.assertEqual(alice_entry.wins, 1)
        self.assertEqual(alice_entry.losses, 0)
        self.assertEqual(bob_entry.wins, 0)
        self.assertEqual(bob_entry.losses, 1)
        self.assertEqual(alice_entry.games_played, 1)
        self.assertEqual(bob_entry.games_played, 1)
        # Started equal, so the exchange is symmetric: one side's gain is the
        # other's loss.
        self.assertEqual(
            alice_entry.rating - DEFAULT_PLAYER_RATING,
            DEFAULT_PLAYER_RATING - bob_entry.rating,
        )

    def test_replaying_an_already_completed_matchup_does_not_double_count(self):
        matchup, alice, bob = _play_to_completion(winner_correct=True)
        alice_before = selectors.get_ranking(player=alice, category=matchup.category)

        match_services.complete_matchup(matchup=matchup)  # idempotent no-op

        alice_after = selectors.get_ranking(player=alice, category=matchup.category)
        self.assertEqual(alice_after.rating, alice_before.rating)
        self.assertEqual(alice_after.games_played, 1)

    def test_a_tie_counts_as_a_draw_for_both_sides(self):
        matchup = make_matchup(question_count=3)
        first, second = matchup.players.all()
        for side in (first, second):
            side.score = 50
            side.total_answer_time_ms = 1000
        MatchupPlayer.objects.bulk_update([first, second], ["score", "total_answer_time_ms"])
        match_services.complete_matchup(matchup=matchup)

        first_entry = selectors.get_ranking(player=first.player, category=matchup.category)
        second_entry = selectors.get_ranking(player=second.player, category=matchup.category)
        self.assertEqual(first_entry.rating, DEFAULT_PLAYER_RATING)  # 0.5 vs 0.5 expected
        self.assertEqual(second_entry.rating, DEFAULT_PLAYER_RATING)
        self.assertEqual(first_entry.wins, 0)
        self.assertEqual(first_entry.losses, 0)
        self.assertEqual(first_entry.games_played, 1)

    def test_abandonment_moves_ratings_exactly_like_any_other_result(self):
        matchup = make_matchup(question_count=3)
        match_services.start_matchup(matchup=matchup)
        leaving, remaining = (side.player for side in matchup.players.all())

        match_services.abandon_matchup(matchup=matchup, leaving_player=leaving)

        remaining_entry = selectors.get_ranking(player=remaining, category=matchup.category)
        leaving_entry = selectors.get_ranking(player=leaving, category=matchup.category)
        self.assertGreater(remaining_entry.rating, DEFAULT_PLAYER_RATING)
        self.assertLess(leaving_entry.rating, DEFAULT_PLAYER_RATING)
        self.assertEqual(remaining_entry.wins, 1)
        self.assertEqual(leaving_entry.losses, 1)


class LadderSelectorTests(TestCase):
    def test_ladder_orders_by_rating_descending_in_one_query(self):
        matchup, alice, bob = _play_to_completion(winner_correct=True)  # alice wins
        category = matchup.category
        with self.assertNumQueries(1):
            standings = list(selectors.ladder(category=category))
        self.assertEqual([entry.player for entry in standings], [alice, bob])

    def test_unrated_players_excludes_anyone_already_seeded(self):
        player = make_player(email="unseeded@example.com")
        category = make_matchup().category
        self.assertIn(player, selectors.unrated_players(category=category))
        ratings.ensure_ranking(player=player, category=category)
        self.assertNotIn(player, selectors.unrated_players(category=category))

    def test_ladder_and_unrated_players_never_surface_a_bot(self):
        # A bot's Ranking is never written in practice (its matchups are
        # never `is_ranked`), but the exclusion is asserted directly rather
        # than relying on that alone — a stray row (a seeded fixture, a
        # manual `ensure_ranking` call) must still never render as a
        # standing.
        bot = make_player(email="cpu@example.com")
        Player.objects.filter(pk=bot.pk).update(is_bot=True)
        category = make_matchup().category
        ratings.ensure_ranking(player=bot, category=category)

        self.assertNotIn(bot, [entry.player for entry in selectors.ladder(category=category)])
        self.assertNotIn(bot, selectors.unrated_players(category=category))


class UnrankedMatchupTests(TestCase):
    """A matchup against a CPU opponent (`Matchup.is_ranked=False`) must
    never move a rating — not the bot's, and not the human's either."""

    def test_create_matchup_marks_a_bot_opponent_unranked(self):
        human = make_player(email="human@example.com")
        bot = make_player(email="cpu-1@example.com")
        Player.objects.filter(pk=bot.pk).update(is_bot=True)
        bot.refresh_from_db()

        matchup = make_matchup(player_one=human, player_two=bot)
        self.assertFalse(matchup.is_ranked)

    def test_create_matchup_between_two_humans_is_ranked(self):
        matchup = make_matchup()
        self.assertTrue(matchup.is_ranked)

    def test_completing_an_unranked_matchup_moves_no_ratings(self):
        human = make_player(email="human-2@example.com")
        bot = make_player(email="cpu-2@example.com")
        Player.objects.filter(pk=bot.pk).update(is_bot=True)
        bot.refresh_from_db()
        matchup = make_matchup(player_one=human, player_two=bot, question_count=3)
        first, second = matchup.players.all()
        for side in (first, second):
            side.score = 50 if side.player == human else 0
        MatchupPlayer.objects.bulk_update([first, second], ["score"])

        match_services.complete_matchup(matchup=matchup)

        self.assertFalse(Ranking.objects.filter(category=matchup.category).exists())

    def test_abandoning_an_unranked_matchup_moves_no_ratings(self):
        human = make_player(email="human-3@example.com")
        bot = make_player(email="cpu-3@example.com")
        Player.objects.filter(pk=bot.pk).update(is_bot=True)
        bot.refresh_from_db()
        matchup = make_matchup(player_one=human, player_two=bot, question_count=3)
        match_services.start_matchup(matchup=matchup)

        match_services.abandon_matchup(matchup=matchup, leaving_player=bot)

        self.assertFalse(Ranking.objects.filter(category=matchup.category).exists())


class SeedAllPlayersTests(TestCase):
    def test_seeds_every_missing_player_and_is_idempotent(self):
        category = make_matchup().category
        make_player(email="one@example.com")
        make_player(email="two@example.com")

        created = ratings.seed_all_players(category=category)
        self.assertEqual(created, Ranking.objects.filter(category=category).count())
        self.assertGreaterEqual(created, 2)

        self.assertEqual(ratings.seed_all_players(category=category), 0)
