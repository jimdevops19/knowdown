"""What a player is allowed to see of a question **once it is over**.

The deliberate opposite of :mod:`apps.questions.api.serializers`, and in its own
module for that reason. That module is the anti-cheat surface: its base class
refuses a field naming an answer at class-creation time, and
``tests.test_serializers`` walks every serializer *declared in it* for the same
names. Putting a reveal serializer there would mean either weakening the check
or carving an exception into it, and an exception inside the mechanism is how
the mechanism stops meaning anything. So the boundary is a **module boundary**:
everything in ``serializers`` is silent, everything here speaks, and which one a
caller reached is visible from the import.

**What makes this safe is the caller, not the payload.** Nothing here decides
who may see an answer; it only knows how to say one. The single caller is
``apps.matches.api.serializers.MatchupQuestionSerializer``, which reaches it only
for a question with a ``completed_at``, inside a view that already refuses a
matchup that is not finished and refuses anyone who did not play in it. Add a
second caller and that reasoning has to be redone there — this module will
answer anybody.

One thing *is* decided here, because it cannot be decided anywhere else: **a
pool that runs long is truncated before it is serialized**, not after. A team
grid's cell accepts every player the two rosters shared, which is hundreds of
names; a client shown five of them with the rest sitting in the response body
would be showing five and *publishing* hundreds. :data:`POOL_REVEAL_LIMIT` names
how many leave the process, and ``total`` says how many there were — the count
is the point of the "… and 340 more" line, and a count is not an answer.

The player's own submission floats to the front of a truncated pool
(``submitted=``): a player who typed a right answer and is then shown five other
right answers, none of them theirs, has been told they were wrong by a screen
that meant to tell them they were right.
"""

from __future__ import annotations

from apps.questions.matching import normalise_answer
from apps.questions.models import QUESTION_MODELS, MatrixKind, QuestionType
from apps.questions.rosters import load_rosters

__all__ = [
    "ANSWER_KEY_BUILDERS",
    "POOL_REVEAL_LIMIT",
    "serialize_answer_key",
]

#: How many accepted answers leave the process for one pool — one free-text
#: question, or one cell of a grid. Five is a screenful on a phone and is the
#: number the box score's modal is laid out for; the rest never crosses the wire,
#: so the client cannot show them however it is patched.
POOL_REVEAL_LIMIT = 5


def _pool(values, *, preferred: str | None) -> dict:
    """``values`` cut to :data:`POOL_REVEAL_LIMIT`, and how many there were.

    ``preferred`` is what this player typed. If it is in the pool it goes first
    and the cut takes the next four; if it is not — they were wrong — the pool is
    shown in its authored order, which for a graded one is most obvious first.
    """
    values = list(values)
    total = len(values)

    if preferred is not None:
        folded = normalise_answer(preferred)
        match = next((v for v in values if normalise_answer(v) == folded), None)
        if match is not None:
            values = [match] + [v for v in values if v is not match]

    return {"accepted": values[:POOL_REVEAL_LIMIT], "total": total}


# --- One builder per question type -------------------------------------------
#
# Plain functions rather than serializers: there is no model field to map and no
# input to validate, only a shape to state, and a ``Serializer`` here would be
# borrowing the vocabulary of the module this one is defined against.


def _correct_option_ids(question, _submitted) -> dict:
    """Single-answer, image-answer and multiple-answer, which reveal the same
    way: the ids of the options that were right.

    **Ids, not text.** The board the box score renders beside this came out of
    ``serialize_for_play`` and names its options by id; a reveal naming them by
    text would have the client matching strings to find which tile to light up,
    and two options worded the same are still two options.
    """
    return {
        "option_ids": [
            option.id for option in question.options.all() if option.is_correct
        ]
    }


def _true_false(question, _submitted) -> dict:
    return {"answer": question.answer}


def _free_text(question, submitted) -> dict:
    """Every spelling that would have been accepted — capped, because a
    generously authored question can carry a dozen and the player needs the
    answer, not the list."""
    typed = submitted.get("text") if isinstance(submitted, dict) else None
    return _pool(
        (answer.value for answer in question.accepted_answers.all()),
        preferred=typed,
    )


def _ordering(question, _submitted) -> dict:
    """The authored arrangement, first to last.

    ``OrderingOption.Meta.ordering`` is ``correct_position``, so the queryset is
    already the answer — which is exactly why the play-time serializer shuffles
    it and this one must not.
    """
    return {"option_ids": [option.id for option in question.options.all()]}


def _matrix(question, submitted) -> dict:
    """Every asked intersection, with its pool cut to
    :data:`POOL_REVEAL_LIMIT`.

    The two kinds of grid (``models.MatrixKind``) keep their answers in different
    places and the difference stops here: an authored grid reads
    ``MatrixCellAnswer`` rows, a team grid asks ``rosters`` who played for both
    franchises, and both come out as a list of names with a total beside it. A
    client cannot tell which it is looking at, and should not have to.
    """
    typed = {}
    if isinstance(submitted, dict):
        typed = {
            (cell.get("row_id"), cell.get("column_id")): cell.get("answer")
            for cell in submitted.get("cells") or []
        }

    cells = []
    for cell in question.cells.select_related("row", "column").all():
        key = (cell.row_id, cell.column_id)
        cells.append(
            {
                "row_id": cell.row_id,
                "column_id": cell.column_id,
                **_pool(_cell_answers(question, cell), preferred=typed.get(key)),
            }
        )
    return {"cells": cells}


def _cell_answers(question, cell):
    """The names that fill one intersection, most obvious first.

    Ordered by ``probability_score`` on both paths — the authored rows by their
    ``Meta.ordering``, the roster players explicitly — because the five that
    survive the cut should be the five a person would actually have thought of.
    The score itself never leaves: it is on ``FORBIDDEN_FIELD_NAMES`` for a live
    board and is no more interesting here, since a revealed answer has nothing
    left to give away.
    """
    if question.kind != MatrixKind.TEAMS:
        return [answer.value for answer in cell.answers.all()]

    rosters = load_rosters()
    players = [
        rosters.player(player_id)
        for player_id in rosters.players_for_all([cell.row.title, cell.column.title])
    ]
    players.sort(key=lambda player: (player.probability_score, player.name))
    return [player.name for player in players]


def _gradual_hints(question, submitted) -> dict:
    """Every box and what filled it — plus the clues, which is the other half of
    reading this question back.

    A gradual-hints board arrives deliberately incomplete and is completed by
    ``hint.revealed`` frames while the clock runs; none of that text is stored
    per matchup, so a box score rendering the board alone would show five empty
    slots and a player wondering what they were even asked. The clues are
    included here rather than on the board for the reason they are paid out one
    at a time in the first place: waiting for them is what the question costs,
    and that price is only paid while the clock is running.
    """
    typed = {}
    if isinstance(submitted, dict):
        typed = {
            field.get("field_id"): field.get("text")
            for field in submitted.get("answer_fields") or []
        }

    return {
        "hints": [hint.text for hint in question.hints.all()],
        "answer_fields": [
            {
                "field_id": field.id,
                "label": field.label,
                **_pool(
                    (answer.value for answer in field.accepted_answers.all()),
                    preferred=typed.get(field.id),
                ),
            }
            for field in question.answer_fields.all()
        ],
    }


#: One builder per question type, keyed the way ``models.QUESTION_MODELS``,
#: ``schemas.answers.ANSWER_SUBMISSIONS``, ``services.evaluation
#: .ANSWER_EVALUATORS`` and ``api.serializers.QUESTION_SERIALIZERS`` are. The
#: fifth sibling registry: a type can be asked, shown, answered, scored — and now
#: explained afterwards — and a test walks all five so none can be the one that
#: was forgotten.
ANSWER_KEY_BUILDERS = {
    QuestionType.SINGLE_ANSWER: _correct_option_ids,
    QuestionType.IMAGE_ANSWER: _correct_option_ids,
    QuestionType.MULTIPLE_ANSWER: _correct_option_ids,
    QuestionType.TRUE_FALSE: _true_false,
    QuestionType.FREE_TEXT: _free_text,
    QuestionType.ORDERING: _ordering,
    QuestionType.MATRIX: _matrix,
    QuestionType.GRADUAL_HINTS: _gradual_hints,
}


def serialize_answer_key(*, question, submitted=None) -> dict:
    """What was actually right, for a question that has been played out.

    ``submitted`` is this viewer's own raw payload (``PlayerAnswer.answer``), or
    ``None`` if they ran out of time. It is used only to order a truncated pool,
    never to decide what is revealed: two players reading the same box score see
    the same answers, possibly in a different order.

    The ``type`` in the result is the discriminator the client switches on, and
    it is the same string the board beside it carries — so a payload whose key
    and board disagree is a bug the client can see rather than one it renders.
    """
    question_type = question.question_type
    builder = ANSWER_KEY_BUILDERS.get(question_type)
    if builder is None:  # pragma: no cover - a registry gap the suite catches
        raise LookupError(f"No answer-key builder for question type {question_type!r}.")

    return {"type": question_type, **builder(question, submitted)}


# Checked at import for the same reason the play-time registry is, and with the
# same consequence: a type nobody wrote a builder for should stop the process,
# not stop one box score halfway down the page.
_unrevealable = set(QUESTION_MODELS) - set(ANSWER_KEY_BUILDERS)
if _unrevealable:  # pragma: no cover - the suite asserts the registries agree
    raise ImportError(
        f"No answer-key builder for question type(s): "
        f"{', '.join(sorted(_unrevealable))}. A finished match could show a "
        f"question it cannot explain."
    )
