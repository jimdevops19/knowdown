"""Was that answer right, and how right?

**The rule this module exists to keep:** evaluation belongs to the questions
domain. ``apps.matches`` must never learn what a correct answer looks like — it
asks this function and gets back a verdict and a number, and stays independent
of the eight answer shapes exactly the way ``selectors.select_questions`` keeps
it independent of the eight tables. The match engine decides what a verdict is
*worth* (speed, points, who won the question); it does not decide what is true.

Three things are settled here, once:

**A malformed payload is not a wrong answer.** An option id from a different
question, an ordering missing an item, a matrix cell nobody was asked to fill —
each raises :class:`ValidationFailed` rather than scoring zero. A client sending
nonsense is a bug, and scoring it as an honest miss would hide it forever; worse,
"anything I do not understand is worth zero" is the behaviour a patched client
probes for. Running out of time is *not* this case: that is the question timing
out, and no payload arrives at all.

**Correctness and credit are two answers.** :class:`AnswerResult` carries both
because they disagree on the types scored per part: a matrix grid with seven of
nine cells right — or a gradual-hints question with two of its three fields —
is not a correct answer, and it is not worth nothing either.

**Partial credit, decided here so step 10 can score against it:**

- single, image, true/false, free text, ordering — all or nothing. Each is one
  indivisible claim; half of an ordering is not half an answer, it is a
  different arrangement.
- multiple answer — the set must match exactly. Per-option credit would make
  selecting every option a strategy worth arithmetic, and "select all that apply"
  where a shotgun scores is not the question that was asked.
- matrix — **per cell**, ``correct / authored``. A grid is genuinely several
  claims, sparse and independent (see ``models.MatrixCell``), and it is the one
  shape where all-or-nothing turns a nine-cell answer into a coin flip on the
  hardest cell.
- gradual hints — **per field**, ``correct / authored``, for the same reason as
  a grid. "Guess the game" asks for a year, a round and a game number, and
  somebody with the first two knew most of it; all-or-nothing would score that
  identically to having no idea.
- name as many — **per popularity point**, ``collected / target``, capped at
  full. The only shape where a right answer is worth *more* than another right
  answer, and the only one where that does not break anything: its board is
  every qualifying player in NBA history rather than a fixed set of claims, so
  the question is how deep you went rather than how much of a board you filled.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from pydantic import TypeAdapter, ValidationError

from apps.core_common.exceptions import ValidationFailed
from apps.questions.career_stats import load_career_stats
from apps.questions.matching import normalise_answer as _normalise
from apps.questions.models import (
    BaseQuestion,
    ColumnsRowsQuestion,
    FreeTextQuestion,
    GradualHintsQuestion,
    MatrixKind,
    MultipleAnswerQuestion,
    NameAsManyQuestion,
    OrderingQuestion,
    QuestionType,
    TrueFalseQuestion,
)
from apps.questions.rosters import load_rosters
from apps.questions.schemas.answers import (
    AnswerSubmission,
    FreeTextSubmission,
    GradualHintsSubmission,
    ImageAnswerSubmission,
    MatrixSubmission,
    MultipleAnswerSubmission,
    NameAsManySubmission,
    OrderingSubmission,
    SingleAnswerSubmission,
    TrueFalseSubmission,
)

__all__ = [
    "ANSWER_EVALUATORS",
    "AnswerResult",
    "evaluate_answer",
    "parse_submission",
]

#: Parses the discriminated union once, at import, rather than per call.
_SUBMISSION_ADAPTER: TypeAdapter = TypeAdapter(AnswerSubmission)


@dataclass(frozen=True)
class AnswerResult:
    """The verdict on one submitted answer.

    ``score`` is *credit*, ``0.0`` to ``1.0`` — the fraction of the question the
    player got right, and nothing to do with points. Points are speed and
    stakes as well as truth, and those are the match engine's to combine
    (``matches.constants``); a scoring curve in here would mean two places
    deciding what a question is worth.

    ``is_correct`` is full credit, not "any credit": it is the flag a scoreboard
    puts a tick beside, and a nine-cell grid with one cell wrong does not get a
    tick.
    """

    is_correct: bool
    score: float

    @classmethod
    def of(cls, score: float) -> AnswerResult:
        return cls(is_correct=score == 1.0, score=score)


WRONG = AnswerResult(is_correct=False, score=0.0)
RIGHT = AnswerResult(is_correct=True, score=1.0)




def _refuse(question: BaseQuestion, problem: str) -> ValidationFailed:
    """A malformed payload, named so a client author can find it.

    Names the question by slug rather than by id, for the reason
    ``shared.logging.labels`` exists: an error mentioning a UUID can only be read
    with a database beside it.
    """
    return ValidationFailed(
        f"Answer to question {question.slug!r} is malformed: {problem}.",
        code="malformed_answer",
    )


# --- One evaluator per answer shape ------------------------------------------


def _evaluate_one_option(
    *,
    question: BaseQuestion,
    submitted: SingleAnswerSubmission | ImageAnswerSubmission,
) -> AnswerResult:
    """single-answer and image-answer: one option id, and it must be one of
    *this* question's.

    Both shapes are the same claim — "this one" — and the options being pictures
    changes only what the client draws, so one evaluator serves both.
    """
    correct_by_id = dict(question.options.values_list("id", "is_correct"))
    if submitted.option_id not in correct_by_id:
        raise _refuse(question, f"option {submitted.option_id} is not one of its options")
    return RIGHT if correct_by_id[submitted.option_id] else WRONG


def _evaluate_multiple(
    *, question: MultipleAnswerQuestion, submitted: MultipleAnswerSubmission
) -> AnswerResult:
    """multiple-answer: the set must match exactly.

    Extra picks are as wrong as missing ones — the question is "which of these",
    and an answer naming an option that is not correct has answered it wrongly
    however many correct ones it also names.
    """
    options = dict(question.options.values_list("id", "is_correct"))
    chosen = set(submitted.option_ids)

    unknown = sorted(chosen - set(options))
    if unknown:
        raise _refuse(
            question,
            f"option(s) {', '.join(map(str, unknown))} are not among its options",
        )

    correct = {option_id for option_id, is_correct in options.items() if is_correct}
    return RIGHT if chosen == correct else WRONG


def _evaluate_true_false(
    *, question: TrueFalseQuestion, submitted: TrueFalseSubmission
) -> AnswerResult:
    return RIGHT if submitted.answer == question.answer else WRONG


def _evaluate_free_text(
    *, question: FreeTextQuestion, submitted: FreeTextSubmission
) -> AnswerResult:
    """free-text: any authored spelling counts.

    A player racing a clock types the short form, which is why a question has as
    many accepted answers as there are honest ways to say it (see
    ``models.FreeTextAnswer``) rather than one canonical string and a fuzzy
    match. Fuzzy matching would be the other way to get here, and it decides on a
    player's behalf how wrong a spelling may be — a threshold nobody can defend
    when it costs somebody the match.
    """
    accepted = {
        _normalise(value)
        for value in question.accepted_answers.values_list("value", flat=True)
    }
    return RIGHT if _normalise(submitted.text) in accepted else WRONG


def _evaluate_ordering(
    *, question: OrderingQuestion, submitted: OrderingSubmission
) -> AnswerResult:
    """ordering: the full arrangement, compared position by position.

    A submission that is not a permutation of the question's items — one missing,
    one repeated, one invented — is malformed rather than wrong: there is no
    arrangement it describes. (The repeat is caught by the schema, which can see
    it without the question; the other two need the question and are caught
    here.)
    """
    positions = dict(question.options.values_list("id", "correct_position"))
    submitted_ids = list(submitted.option_ids)

    if set(submitted_ids) != set(positions):
        raise _refuse(
            question,
            f"an ordering must place each of its {len(positions)} items exactly once, "
            f"got {len(submitted_ids)}",
        )

    expected = sorted(positions, key=lambda option_id: positions[option_id])
    return RIGHT if submitted_ids == expected else WRONG


def _evaluate_matrix(
    *, question: ColumnsRowsQuestion, submitted: MatrixSubmission
) -> AnswerResult:
    """matrix: credit per authored cell.

    The denominator is the cells the question *authored*, not
    ``row_count x column_count``: the grid is sparse, and a player is only asked
    to fill the intersections somebody has a fact about. So a cell left blank
    scores nothing and a cell nobody was asked about is malformed — the
    difference between not knowing an answer and answering a question that was
    not put.

    A cell has **several** accepted answers (``models.MatrixCellAnswer``) and
    any one of them takes the cell: "a player who played for both these teams"
    has as many right answers as the rosters share. ``probability_score`` — how
    obscure a pick is — is deliberately *not* read here: credit is the fraction
    of the grid a player got right, and paying more for a rarer name would make
    two players who both filled the grid correctly score differently.

    A ``kind: teams`` grid answers the same question from the other side — the
    accepted names are looked up rather than stored — and everything above still
    holds: same denominator, same per-cell credit, same refusal for a cell
    nobody was asked about.
    """
    if question.kind == MatrixKind.TEAMS:
        return _evaluate_team_matrix(question=question, submitted=submitted)

    accepted: dict[tuple[int, int], set[str]] = {}
    for row_id, column_id, value in question.cells.values_list(
        "row_id", "column_id", "answers__value"
    ):
        # A cell with no answers cannot be filled in correctly by anybody, so it
        # would silently cap the question's credit. The loader cannot author one
        # (``MatrixCellSpec.answers`` is non-empty) and the admin can; counting
        # it here is what keeps the denominator honest either way.
        cell_answers = accepted.setdefault((row_id, column_id), set())
        if value is not None:
            cell_answers.add(_normalise(value))

    matched = 0
    for cell in submitted.cells:
        key = (cell.row_id, cell.column_id)
        if key not in accepted:
            raise _refuse(
                question,
                f"row {cell.row_id} x column {cell.column_id} is not a cell it asks for",
            )
        if _normalise(cell.answer) in accepted[key]:
            matched += 1

    return AnswerResult.of(matched / len(accepted))


def _evaluate_team_matrix(
    *, question: ColumnsRowsQuestion, submitted: MatrixSubmission
) -> AnswerResult:
    """matrix, ``kind: teams``: the answer key is the roster artifact.

    The cells are still rows in the database — they are what the client draws an
    input in, and what the denominator counts — but they hold no answers, so
    "was this cell filled in correctly?" is a question about two franchises and
    a typed name, and ``apps.questions.rosters`` is what answers it.

    The names are not read from the question, so a grid cannot go stale against
    a trade: re-baking the CSV is the whole update, and no question needs
    reloading for it. What *is* read from the question is which intersections it
    asks about — a cell the loader did not write is refused here exactly as it
    is for an authored grid, because the client should never have shown an input
    for it.
    """
    rosters = load_rosters()
    asked = {
        (row_id, column_id): (row_title, column_title)
        for row_id, column_id, row_title, column_title in question.cells.values_list(
            "row_id", "column_id", "row__title", "column__title"
        )
    }

    # A team grid with no cells is a grid nobody can score. The loader refuses
    # to write one (``schemas.MatrixSpec`` refuses the question outright), and
    # the admin cannot delete the last cell without deleting a heading, so this
    # is the belt to that pair of braces rather than a case anybody has seen.
    if not asked:
        raise _refuse(question, "it asks for no cells at all")

    matched = 0
    for cell in submitted.cells:
        key = (cell.row_id, cell.column_id)
        if key not in asked:
            raise _refuse(
                question,
                f"row {cell.row_id} x column {cell.column_id} is not a cell it asks for",
            )
        if rosters.played_for_all(name=cell.answer, titles=asked[key]):
            matched += 1

    return AnswerResult.of(matched / len(asked))


def _evaluate_gradual_hints(
    *, question: GradualHintsQuestion, submitted: GradualHintsSubmission
) -> AnswerResult:
    """gradual-hints: credit per authored field.

    The denominator is the fields the question *asks for*, not the fields the
    player filled in — otherwise answering one box of three correctly and
    leaving the rest empty would be a perfect answer, and the winning strategy
    would be to type as little as possible.

    Each field is a free-text answer in miniature and is compared exactly as
    one: any authored spelling takes it, folded (``apps.questions.matching``),
    because a player racing a clock types ``7`` rather than ``Game 7``. A field
    naming no box of this question is malformed rather than wrong, the same as a
    matrix cell nobody was asked about — the client should never have drawn an
    input for it.

    The hints themselves are not read here at all. How many of them a player
    waited for changes *when* they answered, which the match engine already
    prices in through response time (``apps.matches.constants.score_answer``);
    paying twice for it — once in speed, once in credit — would be this domain
    deciding what a question is worth.
    """
    accepted: dict[int, set[str]] = {
        field_id: set()
        for field_id in question.answer_fields.values_list("id", flat=True)
    }
    for field_id, value in question.answer_fields.values_list(
        "id", "accepted_answers__value"
    ):
        # A field with no accepted answers cannot be filled in correctly by
        # anybody, so it would silently cap the question's credit. The loader
        # cannot author one (``GradualHintsFieldSpec.accepted_answers`` is
        # non-empty) and the admin can; counting it keeps the denominator honest
        # either way — exactly what ``_evaluate_matrix`` does for an empty cell.
        if value is not None:
            accepted[field_id].add(_normalise(value))

    if not accepted:
        raise _refuse(question, "it asks for no fields at all")

    matched = 0
    for field in submitted.answer_fields:
        if field.field_id not in accepted:
            raise _refuse(
                question, f"field {field.field_id} is not one of its answer fields"
            )
        if _normalise(field.text) in accepted[field.field_id]:
            matched += 1

    return AnswerResult.of(matched / len(accepted))


def _evaluate_name_as_many(
    *, question: NameAsManyQuestion, submitted: NameAsManySubmission
) -> AnswerResult:
    """name-as-many: credit is the popularity points collected, over the
    question's target.

    **The one type where ``probability_score`` is paid rather than hidden.**
    Everywhere else, two players who both filled the board in correctly must
    score the same, and paying more for a rarer name would break that. Here the
    board has no bottom — every qualifying player in NBA history is on it — so
    "how deep did you go?" *is* the question, and a mode that paid a flat rate
    per name would be won by whoever types the five most famous shooters
    fastest. See ``apps.questions.career_stats``.

    Three rules, and each is the counterpart of one an authored type keeps:

    - **A name nobody has is worth nothing, and is not malformed.** Unlike a
      matrix cell that was never asked about, a wrong guess here is an ordinary
      wrong answer — the player was invited to name anybody at all, so there is
      no such thing as naming something they were not asked for. Nothing is
      *deducted* for it either: a mode that punished a guess would be one where
      the right play is to stop typing, which is the opposite of the mode.
    - **The denominator is the question's target, not the board.** Every
      qualifying player is worth hundreds of points and nobody types hundreds of
      names; scoring against the whole board would make full credit unreachable
      and every answer a rounding error. ``target_score`` is the author's
      statement of what a complete answer looks like, checked at load time
      against the points that actually exist.
    - **Credit is capped at 1.0.** A player who beats the target has answered
      the question; there is no extra credit, because points past full credit
      would be this domain deciding what a question is worth, which is
      ``apps.matches``'.
    """
    stats = load_career_stats()
    qualifiers = stats.qualifiers(
        stat=question.stat,
        comparison=question.comparison,
        threshold=question.threshold,
    )

    # A question whose target is zero cannot happen — the schema floors it and
    # the column validates it — but dividing by it here would be a 500 rather
    # than a refusal, and the admin can write one.
    if not question.target_score:
        raise _refuse(question, "it asks for no points at all")

    earned = 0
    for name in submitted.names:
        player = qualifiers.find(name)
        if player is not None:
            earned += player.probability_score

    return AnswerResult.of(min(1.0, earned / question.target_score))


#: One evaluator per question type, keyed the way
#: ``models.QUESTION_MODELS`` and ``schemas.answers.ANSWER_SUBMISSIONS`` are —
#: the three registries are siblings, and adding a question type means adding a
#: line to each. A test walks all three together, so a type with a model and a
#: payload but no evaluator fails the suite rather than the first match that
#: draws one.
ANSWER_EVALUATORS: dict[str, Callable[..., AnswerResult]] = {
    QuestionType.SINGLE_ANSWER: _evaluate_one_option,
    QuestionType.IMAGE_ANSWER: _evaluate_one_option,
    QuestionType.MULTIPLE_ANSWER: _evaluate_multiple,
    QuestionType.TRUE_FALSE: _evaluate_true_false,
    QuestionType.FREE_TEXT: _evaluate_free_text,
    QuestionType.ORDERING: _evaluate_ordering,
    QuestionType.MATRIX: _evaluate_matrix,
    QuestionType.GRADUAL_HINTS: _evaluate_gradual_hints,
    QuestionType.NAME_AS_MANY: _evaluate_name_as_many,
}


# --- The seam the match engine calls -----------------------------------------


def parse_submission(*, payload: Mapping) -> AnswerSubmission:
    """A raw payload as the submission model its ``type`` names.

    The one place a pydantic ``ValidationError`` becomes a
    :class:`ValidationFailed`, the same way ``services.sync`` is the one place a
    resource file's errors do. ``details`` carries every problem rather than the
    first, because a client author fixing a payload wants the whole list — and
    the envelope (``core_common.exceptions``) has a field for exactly that.
    """
    if not isinstance(payload, Mapping):
        raise ValidationFailed(
            "An answer must be an object naming its question type.",
            code="malformed_answer",
        )
    try:
        return _SUBMISSION_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise ValidationFailed(
            "The submitted answer is not a well-formed answer of its type.",
            code="malformed_answer",
            details=[
                f"{'.'.join(str(part) for part in error['loc']) or 'answer'}: "
                f"{error['msg']}"
                for error in exc.errors()
            ],
        ) from exc


def evaluate_answer(*, question: BaseQuestion, submitted: Mapping) -> AnswerResult:
    """Score one player's answer to one question.

    ``submitted`` is the raw payload off the wire. Parsing is not the caller's
    job on purpose: a consumer that parsed first would have to know the union,
    and then the match domain would import the answer shapes it is supposed to
    know nothing about.

    The payload's ``type`` must agree with the question's. It is redundant on the
    happy path — the server chose the question, so it already knows the type —
    and that is the point: a payload disagreeing means the client answered a
    different question than the one on its screen, which is worth a refusal
    rather than an evaluation against whichever row happened to be current.
    """
    evaluator = ANSWER_EVALUATORS.get(question.question_type)
    if evaluator is None:  # pragma: no cover - a registry gap the suite catches
        raise ValidationFailed(
            f"No evaluator for question type '{question.question_type}'.",
            code="unevaluable_question",
        )

    parsed = parse_submission(payload=submitted)
    if parsed.type != question.question_type:
        raise _refuse(
            question,
            f"it is a {parsed.type} answer to a {question.question_type} question",
        )

    return evaluator(question=question, submitted=parsed)
