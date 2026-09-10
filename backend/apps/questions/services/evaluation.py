"""Was that answer right, and how right?

**The rule this module exists to keep:** evaluation belongs to the questions
domain. ``apps.matches`` must never learn what a correct answer looks like — it
asks this function and gets back a verdict and a number, and stays independent
of the seven answer shapes exactly the way ``selectors.select_questions`` keeps
it independent of the seven tables. The match engine decides what a verdict is
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
because they disagree on exactly one type: a matrix grid with seven of nine cells
right is not a correct answer, and it is not worth nothing either.

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
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from pydantic import TypeAdapter, ValidationError

from apps.core_common.exceptions import ValidationFailed
from apps.questions.models import (
    BaseQuestion,
    ColumnsRowsQuestion,
    FreeTextQuestion,
    MultipleAnswerQuestion,
    OrderingQuestion,
    QuestionType,
    TrueFalseQuestion,
)
from apps.questions.schemas.answers import (
    AnswerSubmission,
    FreeTextSubmission,
    ImageAnswerSubmission,
    MatrixSubmission,
    MultipleAnswerSubmission,
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


def _normalise(value: str) -> str:
    """The comparison form of a typed answer.

    Casefolded and whitespace-collapsed, so ``"  kobe   BRYANT "`` matches
    ``"Kobe Bryant"``. Applied to *both* sides, which is what lets the resource
    files stay readable (``accepted_answers`` is authored as people spell it, not
    as a list of lowercase keys) — and why an author cannot accidentally make an
    answer unreachable with a trailing space.

    Casefold rather than lower: it is the one that folds the non-English forms a
    player's keyboard can produce, and a name is exactly the kind of word that
    has them.
    """
    return " ".join(value.split()).casefold()


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
    """
    answers = {
        (row_id, column_id): answer
        for row_id, column_id, answer in question.cells.values_list(
            "row_id", "column_id", "answer"
        )
    }

    matched = 0
    for cell in submitted.cells:
        key = (cell.row_id, cell.column_id)
        if key not in answers:
            raise _refuse(
                question,
                f"row {cell.row_id} x column {cell.column_id} is not a cell it asks for",
            )
        if _normalise(cell.answer) == _normalise(answers[key]):
            matched += 1

    return AnswerResult.of(matched / len(answers))


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
