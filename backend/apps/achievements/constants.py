"""The eight badges, and the numbers their rules are checked against.

Slugs are constants rather than magic strings scattered through
``services.evaluation`` and ``resources/achievements.yaml``, so a rename is a
one-line edit instead of a `grep`. A slug with no matching resource entry is
inert — ``award_achievements_for_matchup`` only awards a badge that is in the
catalog and active — so adding a ninth is a slug here, a rule in
``ACHIEVEMENT_RULES``, and an entry in the YAML, the same three-place pattern
``apps.questions`` uses for a new question type.
"""

from __future__ import annotations

__all__ = [
    "BEAT_HIGHER_RATED",
    "FASTEST_ANSWER",
    "FASTEST_ANSWER_THRESHOLD_MS",
    "FIRST_WIN",
    "FIVE_WINS",
    "FIVE_WIN_STREAK",
    "HUNDRED_QUESTIONS_ANSWERED",
    "PERFECT_MATCH",
    "QUESTIONS_ANSWERED_TARGET",
    "TEN_WINS",
    "WIN_STREAK_TARGET",
]

FIRST_WIN = "first-win"
FIVE_WINS = "five-wins"
TEN_WINS = "ten-wins"
FIVE_WIN_STREAK = "five-win-streak"
PERFECT_MATCH = "perfect-match"
HUNDRED_QUESTIONS_ANSWERED = "hundred-questions-answered"
FASTEST_ANSWER = "fastest-answer"
BEAT_HIGHER_RATED = "beat-higher-rated"

#: Consecutive wins "5 Win Streak" asks for. A streak is read from at most this
#: many of a player's most recent completed matchups — enough to tell whether
#: the badge is earned, and no more needs reading.
WIN_STREAK_TARGET = 5

#: Total ``PlayerAnswer`` rows "100 Questions Answered" asks for — every
#: question a player has ever been asked, right or wrong, in any category.
QUESTIONS_ANSWERED_TARGET = 100

#: How fast is "Fastest Answer", against a ten-second clock
#: (``apps.matches.constants.FALLBACK_QUESTION_TIME_LIMIT_MS``). Correct
#: only — a fast guess is still a guess.
FASTEST_ANSWER_THRESHOLD_MS = 1500
