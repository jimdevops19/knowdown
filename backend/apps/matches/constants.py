"""The numbers the match engine is measured against.

Sits beside ``apps.questions.constants`` in spirit — a statement about the
*game* rather than the catalog — and the two are independent for the same
reason ``evaluation`` and ``matches`` are: this module decides what a verdict
is *worth*, never what is true. ``apps.questions.services.evaluation`` hands
back ``AnswerResult(is_correct, score)``; everything below turns that plus a
server-measured response time into points.
"""

from __future__ import annotations

from apps.questions.models import QuestionType

__all__ = [
    "DEFAULT_PLAYER_RATING",
    "MATCH_QUESTION_COUNTS",
    "MAX_QUESTION_POINTS",
    "MIN_SPEED_FACTOR",
    "PLAYERS_PER_MATCHUP",
    "POOL_WAITING_TTL_SECONDS",
    "PRESENCE_TTL_SECONDS",
    "QUESTION_TIME_LIMIT_MS",
    "QUESTION_TIME_LIMIT_SECONDS",
    "QUESTION_TIME_LIMITS_MS",
    "RECONNECT_GRACE_SECONDS",
    "score_answer",
    "time_limit_ms_for",
]

#: How many questions a matchup plays. Chosen once per matchup
#: (``random.choice``), for both players — never per question, or the length
#: of a game would depend on how the dice landed on question one.
MATCH_QUESTION_COUNTS: tuple[int, ...] = (3, 5, 7)

#: A matchup is a race between exactly two players. Enforced by a DB
#: constraint on ``MatchupPlayer`` as well as here, the way display-name
#: uniqueness is enforced twice in ``apps.players``.
PLAYERS_PER_MATCHUP = 2

#: A player entering a category with no ``apps.rankings.Ranking`` row yet
#: starts here. Lives beside the match numbers rather than in ``rankings``
#: because seeding happens the moment a matchup needs a rating that is not
#: there yet, not on a schedule ``rankings`` owns.
DEFAULT_PLAYER_RATING = 1000

#: How long a question stays open once ``start_question`` stamps it, in
#: server time. The client displays a countdown from this number; it is never
#: read back from the client. This is the *default* — the per-type override
#: below is what most questions get.
QUESTION_TIME_LIMIT_SECONDS = 10
QUESTION_TIME_LIMIT_MS = QUESTION_TIME_LIMIT_SECONDS * 1000

#: Per-``QuestionType`` overrides of the above. A matrix question is several
#: sparse, independent claims read off a grid (``evaluation`` scores it "per
#: authored cell" for the same reason) rather than one glance-and-answer
#: claim, so it earns more clock than the default — a type absent here just
#: falls back to ``QUESTION_TIME_LIMIT_MS`` in ``time_limit_ms_for``. Keyed by
#: type, not by category: a board is drawn from one category but categories
#: are independent of question types on purpose (``backend/CLAUDE.md``), so
#: this has to live wherever "how long is fair" is decided, not wherever
#: "what is this about" is decided.
QUESTION_TIME_LIMITS_MS: dict[QuestionType, int] = {
    QuestionType.MATRIX: 20_000,
}


def time_limit_ms_for(question_type: QuestionType) -> int:
    """How long a question of this type stays open, in server time.

    The one place both ``services`` (measuring an answer against the clock)
    and the realtime transport (telling a client how long to count down from,
    and how long its own watchdog should sleep) ask this question, so the two
    can never quietly disagree about when a question closes.
    """
    return QUESTION_TIME_LIMITS_MS.get(question_type, QUESTION_TIME_LIMIT_MS)

#: What a fully correct, instant answer is worth.
MAX_QUESTION_POINTS = 100

#: The floor of the speed multiplier. Even an answer submitted with one
#: millisecond left on the clock is still worth this fraction of
#: ``MAX_QUESTION_POINTS`` — a hard question worked out right up to the wire
#: is not scored as though it were a guess, and a wrong answer is never made
#: worse by taking the full ten seconds to be wrong.
MIN_SPEED_FACTOR = 0.5

#: How long a player may sit as "the one waiting" in a category's matchmaking
#: pool before the slot is considered stale and free for someone else to claim
#: (``apps.matches.pool``). A safety net for a process that died mid-wait, not
#: the normal path out — the normal path is pairing or an explicit leave.
POOL_WAITING_TTL_SECONDS = 60

#: How long a presence entry (``apps.matches.presence``) survives with no
#: refresh before a player is treated as offline. Short, because presence is a
#: "right now" signal, not a record — a crashed process must not strand
#: someone as permanently online.
PRESENCE_TTL_SECONDS = 30

#: How long a mid-match disconnect is given to reconnect before the opponent is
#: awarded the win (``services.abandon_matchup``). Long enough for a phone to
#: survive a tunnel or a tab reload, short enough that the opponent is not left
#: staring at a paused game.
RECONNECT_GRACE_SECONDS = 20


def score_answer(*, credit: float, response_time_ms: int, time_limit_ms: int = QUESTION_TIME_LIMIT_MS) -> int:
    """Points for one answer: correctness first, speed second.

    ``credit`` is ``AnswerResult.score`` — 0.0 to 1.0, already decided by
    ``apps.questions`` — never ``is_correct``, so the one shape where they
    disagree (a matrix) is paid for the cells actually right rather than
    rounded down to zero.

    A wrong answer (``credit == 0``) is worth nothing, whatever the speed —
    speed only multiplies an answer that was already worth something, so
    guessing fast is never better than answering right slowly. ``response_time_ms``
    is clamped to ``[0, time_limit_ms]`` by the caller (``services.submit_answer``);
    this function does not re-derive it from a clock, so it can be called from a
    test with any number and stay honest about what it is measuring.
    """
    if credit <= 0:
        return 0
    remaining_fraction = max(0.0, (time_limit_ms - response_time_ms) / time_limit_ms)
    speed_factor = MIN_SPEED_FACTOR + (1 - MIN_SPEED_FACTOR) * remaining_fraction
    return round(MAX_QUESTION_POINTS * credit * speed_factor)
