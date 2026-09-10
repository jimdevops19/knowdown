"""Step 18: badges checked from the match result, once, and never twice.

Every test plays real matches through ``apps.matches.services`` — the actual
integration point — rather than calling the rules in isolation, the way
``apps.rankings.tests.test_ratings`` exercises ``complete_matchup`` directly.
"""

from __future__ import annotations

from django.test import TestCase

from apps.achievements import constants
from apps.achievements.models import PlayerAchievement
from apps.achievements.services import sync_achievements
from apps.achievements.tests.factories import give_answer_history, play_matchup
from apps.matches import services as match_services
from apps.players.tests.factories import make_player
from apps.rankings.models import Ranking
from apps.rankings.services import ensure_ranking


def _earned(*, player, slug: str) -> bool:
    return PlayerAchievement.objects.filter(
        player=player, achievement__slug=slug
    ).exists()


class FirstWinTests(TestCase):
    def setUp(self) -> None:
        sync_achievements()

    def test_the_winner_earns_it_the_loser_does_not(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)

        self.assertTrue(_earned(player=alice, slug=constants.FIRST_WIN))
        self.assertFalse(_earned(player=bob, slug=constants.FIRST_WIN))

    def test_a_second_win_does_not_grant_it_twice(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        first = PlayerAchievement.objects.get(player=alice, achievement__slug=constants.FIRST_WIN)

        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)

        self.assertEqual(
            PlayerAchievement.objects.filter(
                player=alice, achievement__slug=constants.FIRST_WIN
            ).count(),
            1,
        )
        second = PlayerAchievement.objects.get(player=alice, achievement__slug=constants.FIRST_WIN)
        self.assertEqual(first.pk, second.pk)  # the same row — never replaced


class CumulativeWinTests(TestCase):
    def setUp(self) -> None:
        sync_achievements()

    def test_five_wins_and_a_streak_then_ten_wins(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")

        for _ in range(4):
            play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        self.assertFalse(_earned(player=alice, slug=constants.FIVE_WINS))

        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)  # 5th
        self.assertTrue(_earned(player=alice, slug=constants.FIVE_WINS))
        self.assertTrue(_earned(player=alice, slug=constants.FIVE_WIN_STREAK))
        self.assertFalse(_earned(player=alice, slug=constants.TEN_WINS))

        for _ in range(5):
            play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        self.assertTrue(_earned(player=alice, slug=constants.TEN_WINS))

    def test_a_loss_breaks_the_streak(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")

        for _ in range(4):
            play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        # Alice loses the fifth outright — bob answers right, she doesn't.
        play_matchup(alice=alice, bob=bob, alice_correct=False, bob_correct=True)
        self.assertFalse(_earned(player=alice, slug=constants.FIVE_WIN_STREAK))

        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        self.assertFalse(_earned(player=alice, slug=constants.FIVE_WIN_STREAK))  # only 1 in a row


class PerfectMatchTests(TestCase):
    def setUp(self) -> None:
        sync_achievements()

    def test_answering_every_question_correctly_earns_it(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        play_matchup(alice=alice, bob=bob, question_count=3, alice_correct=True, bob_correct=True)
        self.assertTrue(_earned(player=alice, slug=constants.PERFECT_MATCH))
        self.assertTrue(_earned(player=bob, slug=constants.PERFECT_MATCH))  # both perfect, tie

    def test_missing_even_one_question_does_not_earn_it(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        play_matchup(alice=alice, bob=bob, question_count=3, alice_correct=True, bob_correct=False)
        self.assertFalse(_earned(player=bob, slug=constants.PERFECT_MATCH))


class FastestAnswerTests(TestCase):
    def setUp(self) -> None:
        sync_achievements()

    def test_a_correct_answer_at_the_wire_does_not_earn_it(self):
        # play_matchup submits immediately (well under the threshold in real
        # wall-clock time on the test DB) — see the instant-answer test in
        # apps.matches for the same assumption. Here the point is the other
        # direction: a late, correct answer must not qualify.
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)

        from apps.matches.models import PlayerAnswer

        PlayerAnswer.objects.filter(
            matchup_question__matchup=matchup, player=alice
        ).update(response_time_ms=constants.FASTEST_ANSWER_THRESHOLD_MS + 1)
        # The badge was already awarded from the fast submission above; the
        # point of this test is the rule itself, exercised directly against
        # the row it reads.
        from apps.achievements.services.evaluation import _check_fastest_answer

        question = matchup.players.get(player=alice)
        self.assertFalse(
            _check_fastest_answer(matchup=matchup, player=alice, side=question)
        )

    def test_a_fast_correct_answer_earns_it(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        self.assertTrue(_earned(player=alice, slug=constants.FASTEST_ANSWER))


class HundredQuestionsAnsweredTests(TestCase):
    def setUp(self) -> None:
        sync_achievements()

    def test_crossing_the_threshold_earns_it(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        give_answer_history(player=alice, count=97)  # short of the target

        matchup = play_matchup(  # +3 real answers, crossing 100
            alice=alice, bob=bob, question_count=3, alice_correct=True, bob_correct=False
        )

        self.assertTrue(_earned(player=alice, slug=constants.HUNDRED_QUESTIONS_ANSWERED))
        self.assertFalse(_earned(player=bob, slug=constants.HUNDRED_QUESTIONS_ANSWERED))
        self.assertEqual(matchup.status, matchup.Status.COMPLETED)

    def test_short_of_the_threshold_does_not_earn_it(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        give_answer_history(player=alice, count=50)
        play_matchup(alice=alice, bob=bob, question_count=3, alice_correct=True, bob_correct=False)
        self.assertFalse(_earned(player=alice, slug=constants.HUNDRED_QUESTIONS_ANSWERED))


class BeatHigherRatedTests(TestCase):
    def setUp(self) -> None:
        sync_achievements()

    def _set_rating(self, *, player, category, rating: int) -> None:
        entry = ensure_ranking(player=player, category=category)
        Ranking.objects.filter(pk=entry.pk).update(rating=rating)

    def test_the_underdog_earns_it_on_an_upset(self):
        alice = make_player(email="alice@example.com")  # the favourite
        bob = make_player(email="bob@example.com")  # the underdog, who wins
        matchup = play_matchup(alice=alice, bob=bob, alice_correct=False, bob_correct=True)
        # `play_matchup` already completed one match at equal (default)
        # ratings; rate them apart and play again so there is something to
        # be an upset relative to.
        self._set_rating(player=alice, category=matchup.category, rating=1400)
        self._set_rating(player=bob, category=matchup.category, rating=1000)

        play_matchup(
            alice=alice, bob=bob, category=matchup.category,
            alice_correct=False, bob_correct=True,
        )
        self.assertTrue(_earned(player=bob, slug=constants.BEAT_HIGHER_RATED))
        self.assertFalse(_earned(player=alice, slug=constants.BEAT_HIGHER_RATED))

    def test_the_favourite_winning_does_not_earn_it(self):
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        self._set_rating(player=alice, category=matchup.category, rating=1400)
        self._set_rating(player=bob, category=matchup.category, rating=1000)

        play_matchup(
            alice=alice, bob=bob, category=matchup.category,
            alice_correct=True, bob_correct=False,
        )
        self.assertFalse(_earned(player=alice, slug=constants.BEAT_HIGHER_RATED))


class InactiveAchievementTests(TestCase):
    def test_a_deactivated_badge_cannot_be_newly_earned(self):
        sync_achievements()
        from apps.achievements.models import Achievement

        Achievement.objects.filter(slug=constants.FIRST_WIN).update(is_active=False)

        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)

        self.assertFalse(_earned(player=alice, slug=constants.FIRST_WIN))


class NoCatalogLoadedTests(TestCase):
    def test_awarding_is_a_no_op_when_nothing_has_been_synced(self):
        """``award_achievements_for_matchup`` must not blow up a real match
        just because nobody has run ``sync_achievements`` yet."""
        alice = make_player(email="alice@example.com")
        bob = make_player(email="bob@example.com")
        matchup = play_matchup(alice=alice, bob=bob, alice_correct=True, bob_correct=False)
        self.assertEqual(matchup.status, matchup.Status.COMPLETED)
        self.assertEqual(PlayerAchievement.objects.count(), 0)
