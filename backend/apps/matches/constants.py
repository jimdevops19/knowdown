"""The numbers the match engine is measured against.

Sits beside ``apps.questions.constants`` in spirit — a statement about the
*game* rather than the catalog — and the two are independent for the same
reason ``evaluation`` and ``matches`` are: this module decides what a verdict
is *worth*, never what is true. ``apps.questions.services.evaluation`` hands
back ``AnswerResult(is_correct, score)``; everything below turns that plus a
server-measured response time into points.
"""

from __future__ import annotations

from apps.questions.constants import DEFAULT_TIME_LIMIT_SECONDS
from apps.questions.models import QuestionType

__all__ = [
    "DEFAULT_PLAYER_RATING",
    "FALLBACK_QUESTION_TIME_LIMIT_MS",
    "FALLBACK_QUESTION_TIME_LIMIT_SECONDS",
    "LATE_ANSWER_FLOOR_MS",
    "MATCH_QUESTION_COUNTS",
    "MAX_QUESTION_POINTS",
    "MAX_TIEBREAKER_QUESTIONS",
    "MIN_SPEED_FACTOR",
    "PLAYERS_PER_MATCHUP",
    "POOL_WAITING_TTL_SECONDS",
    "PRESENCE_TTL_SECONDS",
    "PRE_QUESTION_INFO_MS",
    "QUESTION_READ_DELAY_MS",
    "SPEED_SCORED_TYPES",
    "QUESTION_READ_DELAY_SECONDS",
    "RECONNECT_GRACE_SECONDS",
    "read_delay_ms_for",
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
#: server time, when *nothing* says otherwise. The client displays a countdown
#: from this number; it is never read back from the client. "Fallback" because
#: a question ordinarily outranks it with a ``time_limit_seconds`` of its own
#: — written by its author, or handed down by the resource file its whole
#: answer shape is authored in (``apps.questions.schemas.QuestionFileSpec``).
#: See ``time_limit_ms_for``.
#:
#: The number itself belongs to the questions domain
#: (``apps.questions.constants.DEFAULT_TIME_LIMIT_SECONDS``), which is where
#: the loader validates hint schedules against it; this is the alias the
#: engine and its tests name it by, and an alias rather than a second ten so
#: the clock a file is checked against and the clock a match counts down
#: cannot drift apart.
FALLBACK_QUESTION_TIME_LIMIT_SECONDS = DEFAULT_TIME_LIMIT_SECONDS
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


#: How long a question's task screen ("Click to order from earliest to latest")
#: owns the whole display before the question itself appears, for the questions
#: that have one (``apps.questions.models.BaseQuestion.pre_question_info``).
#:
#: **Added to the read delay, never taken out of it.** The three seconds below
#: are the beat spent reading *this question*; a player who spent them learning
#: what an ordering board is has not read the question, and would meet the
#: clock having done half the job the delay is there for. So a question with a
#: task screen is simply dealt earlier: its ``started_at`` is stamped this much
#: further out, and everything measured from that stamp — scoring, the
#: deadline, the watchdog, a gradual-hints reveal — moves with it, which is the
#: same property that lets the read delay itself be changed by editing one
#: number.
#:
#: Long enough to read a line of instruction twice and short enough that a
#: player who already knows the type is not made to sit through it; mirrored on
#: the frontend by ``PRE_QUESTION_INFO_MS`` (``frontend/src/lib/config.ts``),
#: which is what splits the window into "task screen" and "read the question".
PRE_QUESTION_INFO_MS = 2_500


def read_delay_ms_for(*, pre_question_info: str = "") -> int:
    """How long one question is on screen before its clock starts.

    The ordinary :data:`QUESTION_READ_DELAY_MS`, plus
    :data:`PRE_QUESTION_INFO_MS` for a question that says what the task is
    first. A function for :func:`time_limit_ms_for`'s reason: the stamp and
    everything that has to sleep past it are computed in different modules, and
    two of them deciding this separately is one of them being wrong.
    """
    if pre_question_info:
        return QUESTION_READ_DELAY_MS + PRE_QUESTION_INFO_MS
    return QUESTION_READ_DELAY_MS


def time_limit_ms_for(*, override_seconds: int | None = None) -> int:
    """How long one question stays open, in server time.

    ``override_seconds`` is the question's own ``time_limit_seconds``, straight
    off its row — which is where every tier above this one has already been
    resolved: an entry's authored number, or the clock its resource file sets
    for the whole answer shape, written into the row by the loader
    (``apps.questions.schemas.QuestionFileSpec``). ``None`` means no file and
    no author ever named one, and the question plays at the ordinary
    :data:`FALLBACK_QUESTION_TIME_LIMIT_SECONDS`.

    A function rather than an inlined ``or`` at each call site because this app
    owns *when a question closes*: ``services`` (measuring an answer against
    the clock), the realtime transport (telling a client how long to count down
    from, and how long its own watchdog should sleep) and the bots all ask here,
    so the four can never quietly disagree.
    """
    if override_seconds is not None:
        return override_seconds * 1000
    return FALLBACK_QUESTION_TIME_LIMIT_MS


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

#: How much of the end of the clock is all scored as "at the wire".
#:
#: An answer arriving with less than this left is timed at the full limit, so it
#: is paid :data:`MIN_SPEED_FACTOR` exactly rather than a hair above it. The
#: reason is the boards that send *themselves* at the whistle: multiple-answer,
#: matrix and gradual-hints all commit whatever the player has in hand a beat
#: before the question closes (``AUTO_SUBMIT_LEAD_MS``, which this mirrors),
#: because work that was never submitted is worth nothing at all. That lead is
#: network margin, not thinking time, and without this window a player who ran
#: out of time would be paid fractionally *more* than the floor for the slow
#: phone that sent their answer earliest.
#:
#: A human answering inside the same last second is paid the floor too, which is
#: the right answer for the same reason: a fifth of a second either side of the
#: whistle is not a difference in how well anybody knew the question.
LATE_ANSWER_FLOOR_MS = 1_000

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

    The last :data:`LATE_ANSWER_FLOOR_MS` of the clock are all scored at
    :data:`MIN_SPEED_FACTOR` — see that constant for why the boards that submit
    themselves at the whistle need the end of the curve to be flat.

    ``question_type`` decides whether speed applies at all — see
    :data:`SPEED_SCORED_TYPES`. It is optional, and an unstated type is scored
    on speed, because that is what every type but one does and a caller that
    does not know the type is a caller answering an ordinary question.
    """
    if credit <= 0:
        return 0
    if question_type is not None and question_type not in SPEED_SCORED_TYPES:
        return round(MAX_QUESTION_POINTS * credit)
    # Never more than half the clock, so a question authored with a very short
    # one (``time_limit_seconds`` may be as low as 1) still has a curve to speak
    # of rather than paying the floor for every answer to it.
    at_the_wire_ms = min(LATE_ANSWER_FLOOR_MS, time_limit_ms / 2)
    if response_time_ms >= time_limit_ms - at_the_wire_ms:
        return round(MAX_QUESTION_POINTS * credit * MIN_SPEED_FACTOR)
    remaining_fraction = max(0.0, (time_limit_ms - response_time_ms) / time_limit_ms)
    speed_factor = MIN_SPEED_FACTOR + (1 - MIN_SPEED_FACTOR) * remaining_fraction
    return round(MAX_QUESTION_POINTS * credit * speed_factor)
