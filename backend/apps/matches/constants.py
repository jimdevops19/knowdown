"""The numbers the match engine is measured against.

Sits beside ``apps.questions.constants`` in spirit — a statement about the
*game* rather than the catalog — and the two are independent for the same
reason ``evaluation`` and ``matches`` are: this module decides what a verdict
is *worth*, never what is true. ``apps.questions.services.evaluation`` hands
back ``AnswerResult(is_correct, score)``; everything below turns that plus a
server-measured response time into points.
"""

from __future__ import annotations

from apps.questions.models import QUESTION_MODELS, BaseQuestion, QuestionType

__all__ = [
    "DEFAULT_PLAYER_RATING",
    "FALLBACK_QUESTION_TIME_LIMIT_MS",
    "FALLBACK_QUESTION_TIME_LIMIT_SECONDS",
    "MATCH_QUESTION_COUNTS",
    "MAX_QUESTION_POINTS",
    "MAX_TIEBREAKER_QUESTIONS",
    "MIN_SPEED_FACTOR",
    "PLAYERS_PER_MATCHUP",
    "POOL_WAITING_TTL_SECONDS",
    "PRESENCE_TTL_SECONDS",
    "QUESTION_READ_DELAY_MS",
    "SPEED_SCORED_TYPES",
    "QUESTION_READ_DELAY_SECONDS",
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

#: How many sudden-death questions a level match may be extended by before
#: the engine stops asking (``apps.matches.services.tiebreak``). A cap rather
#: than "until someone wins" because two players who have matched each other
#: point for point through seven questions can keep doing it, and a match that
#: cannot end is worse than one that ends on the tie rules
#: ``services.complete_matchup`` already has (total answer time, then no
#: winner at all). Three is enough that the overwhelming majority of ties are
#: settled by play rather than by stopwatch, and short enough that the extra
#: round is still recognisably an overtime.
MAX_TIEBREAKER_QUESTIONS = 3

#: A player entering a category with no ``apps.rankings.Ranking`` row yet
#: starts here. Lives beside the match numbers rather than in ``rankings``
#: because seeding happens the moment a matchup needs a rating that is not
#: there yet, not on a schedule ``rankings`` owns.
DEFAULT_PLAYER_RATING = 1000

#: How long a question stays open once ``start_question`` stamps it, in
#: server time, when *nothing more specific* says otherwise. The client
#: displays a countdown from this number; it is never read back from the
#: client. "Fallback" because a question may outrank it with a
#: ``time_limit_seconds`` of its own — see ``time_limit_ms_for``.
#:
#: The number itself belongs to the question models
#: (``BaseQuestion.DEFAULT_TIME_LIMIT_SECONDS``): what an ordinary question is
#: worth on the clock is a property of its answer shape, and each shape states
#: its own beside the fields that justify it. This is the alias the engine and
#: its tests name it by, so nothing here has to reach for a model class to say
#: "the ordinary clock".
FALLBACK_QUESTION_TIME_LIMIT_SECONDS = BaseQuestion.DEFAULT_TIME_LIMIT_SECONDS
FALLBACK_QUESTION_TIME_LIMIT_MS = FALLBACK_QUESTION_TIME_LIMIT_SECONDS * 1000

#: How long a question is on screen before its clock starts running — time to
#: read it before the countdown (and eligibility to be timed out) begins.
#: ``start_question`` stamps ``MatchupQuestion.started_at`` this far in the
#: future of the moment the question is dealt, rather than stamping "now" and
#: delaying the broadcast: the board still reaches the client immediately, so
#: nothing here is a loading spinner, and a submission that lands during this
#: window is simply timed at effectively zero elapsed rather than refused —
#: there is no separate "not open yet" state to reject it with. Everything
#: downstream that reasons about the clock (``submit_answer``'s time-limit
#: check, ``complete_question``'s deadline, the realtime watchdog's sleep)
#: reads ``started_at`` rather than "whenever the question was dealt", so all
#: three shift together automatically and cannot drift out of step with each
#: other. Mirrored on the frontend by ``QUESTION_READ_DELAY_MS``
#: (``frontend/src/lib/config.ts``) purely to draw a matching, non-ticking
#: bar during the delay — the number here is the one that actually gates
#: scoring and the forced close.
QUESTION_READ_DELAY_SECONDS = 3
QUESTION_READ_DELAY_MS = QUESTION_READ_DELAY_SECONDS * 1000


def time_limit_ms_for(*, question_type: QuestionType, override_seconds: int | None = None) -> int:
    """How long one question stays open, in server time.

    Two tiers, most specific first: ``override_seconds`` — the question's own
    authored ``time_limit_seconds``, straight off its row, ``None`` when the
    author left it unset; and the default for its *kind*, the
    ``DEFAULT_TIME_LIMIT_SECONDS`` on the model that shape is stored in, which
    is ten seconds for every type that does not say otherwise
    (:data:`FALLBACK_QUESTION_TIME_LIMIT_SECONDS`).

    Looked up through ``QUESTION_MODELS`` rather than through a table here, so
    a new question type arrives with its own clock already decided — a type
    that is added to the registry and forgotten here is not a type quietly
    playing at somebody else's tempo. This app still owns the *tiers*: it is
    the one place both ``services`` (measuring an answer against the clock) and
    the realtime transport (telling a client how long to count down from, and
    how long its own watchdog should sleep) ask the question, so the two can
    never quietly disagree about when a question closes.
    """
    if override_seconds is not None:
        return override_seconds * 1000
    model = QUESTION_MODELS.get(question_type)
    if model is None:
        return FALLBACK_QUESTION_TIME_LIMIT_MS
    return model.DEFAULT_TIME_LIMIT_SECONDS * 1000


#: What a fully correct, instant answer is worth.
MAX_QUESTION_POINTS = 100

#: The types where answering *sooner* is worth more — every type but one.
#:
#: Stated as the set that **is** speed-scored rather than the exception list,
#: because the day a second such type arrives the question to ask is "is this
#: one a race?", and a list of exceptions asks the opposite one.
#:
#: ``name-as-many`` is out because its clock is not a deadline to beat but a
#: *budget to spend*: the question is "how many can you name in thirty
#: seconds", and a curve paying 100 for a complete answer at one second and 50
#: for the same answer at twenty-nine would be paying players to stop typing —
#: which is the only strategy this mode must not reward. The race is still a
#: race: both players are spending the same thirty seconds, and the winner is
#: the one who went deeper in them.
SPEED_SCORED_TYPES: frozenset[str] = frozenset(
    question_type
    for question_type in QuestionType.values
    if question_type != QuestionType.NAME_AS_MANY
)

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


def score_answer(
    *,
    credit: float,
    response_time_ms: int,
    time_limit_ms: int = FALLBACK_QUESTION_TIME_LIMIT_MS,
    question_type: QuestionType | str | None = None,
) -> int:
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

    ``question_type`` decides whether speed applies at all — see
    :data:`SPEED_SCORED_TYPES`. It is optional, and an unstated type is scored
    on speed, because that is what every type but one does and a caller that
    does not know the type is a caller answering an ordinary question.
    """
    if credit <= 0:
        return 0
    if question_type is not None and question_type not in SPEED_SCORED_TYPES:
        return round(MAX_QUESTION_POINTS * credit)
    remaining_fraction = max(0.0, (time_limit_ms - response_time_ms) / time_limit_ms)
    speed_factor = MIN_SPEED_FACTOR + (1 - MIN_SPEED_FACTOR) * remaining_fraction
    return round(MAX_QUESTION_POINTS * credit * speed_factor)
