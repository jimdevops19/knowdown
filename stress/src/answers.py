"""A plausible, valid-shaped submission for whatever board the server sent.

Never a *correct* one on purpose. Whether the evaluator gets the verdict right
is already settled by ``apps.questions.tests.test_evaluation``; what this
rehearses is the load of an answer arriving — the write, the scoring, the
broadcast, the close — under eighty players doing it at once. A driver that
also tried to be right would be one whose numbers moved when somebody edited
a question.

Every branch mirrors one variant of ``apps.questions.schemas.answers
.AnswerSubmission``, and there is a branch for **every** type the catalog
serves (``backend/apps/questions/resources/nba/_active.yaml`` lists nine).
A type with no branch would sink one player's whole match, which is exactly
the kind of client-side hole that reads on the console as a platform failure.
"""

from __future__ import annotations

import random

#: Names for the two open-ended types. Deliberately nonsense — see above; a
#: real player name would make the run's scores depend on the catalog.
_GUESS_WORDS = [
    "stress", "rehearsal", "placeholder", "sample", "dummy", "synthetic",
]


def build_answer(board: dict, rng: random.Random) -> dict:
    """The payload to send for ``board``, as an ``ANSWER_SUBMIT`` ``payload``."""
    question_type = board["type"]
    builder = _BUILDERS.get(question_type)
    if builder is None:
        raise ValueError(f"Unknown question type from the server: {question_type!r}")
    return builder(board, rng)


def _single(board: dict, rng: random.Random) -> dict:
    option = rng.choice(board["options"])
    return {"type": board["type"], "option_id": option["id"]}


def _multiple(board: dict, rng: random.Random) -> dict:
    options = board["options"]
    chosen = rng.sample(options, rng.randint(1, len(options)))
    return {"type": board["type"], "option_ids": [o["id"] for o in chosen]}


def _true_false(board: dict, rng: random.Random) -> dict:
    return {"type": board["type"], "answer": rng.choice([True, False])}


def _free_text(board: dict, rng: random.Random) -> dict:
    return {"type": board["type"], "text": _guess(rng)}


def _ordering(board: dict, rng: random.Random) -> dict:
    # An ordering submission is the *whole* sequence, not a subset — the
    # schema refuses a partial one, so shuffling the ids the board gave is
    # the only valid shape there is.
    option_ids = [o["id"] for o in board["options"]]
    rng.shuffle(option_ids)
    return {"type": board["type"], "option_ids": option_ids}


def _matrix(board: dict, rng: random.Random) -> dict:
    return {
        "type": board["type"],
        "cells": [
            {
                "row_id": cell["row_id"],
                "column_id": cell["column_id"],
                "answer": _guess(rng),
            }
            for cell in board["cells"]
        ],
    }


def _gradual_hints(board: dict, rng: random.Random) -> dict:
    """Every box, filled in.

    A partly filled submission is valid too (and is what a real player who ran
    out of clock sends), but filling all of them is the heavier write and the
    one that exercises per-field scoring rather than skipping it. The clues
    arriving meanwhile as ``hint.revealed`` frames are the point of this type
    for the *transport*, and the play loop counts them.
    """
    return {
        "type": board["type"],
        "answer_fields": [
            {"field_id": field["id"], "text": _guess(rng)}
            for field in board["answer_fields"]
        ],
    }


def _name_as_many(board: dict, rng: random.Random) -> dict:
    """A list of names, each distinct after case-folding.

    The schema refuses two names that fold to the same thing, so the index is
    part of every entry rather than trusting a sample not to repeat. The
    length is drawn well under ``max_names``: this type's clock is a budget to
    spend, and a player who filled the cap every single time is not what a
    room of people typing looks like.
    """
    cap = min(int(board.get("max_names", 20)), 20)
    count = rng.randint(1, max(1, cap // 2))
    return {
        "type": board["type"],
        "names": [f"{_guess(rng)} {index}" for index in range(count)],
    }


_BUILDERS = {
    "single-answer": _single,
    "image-answer": _single,
    "multiple-answer": _multiple,
    "true-false": _true_false,
    "free-text": _free_text,
    "ordering": _ordering,
    "matrix": _matrix,
    "gradual-hints": _gradual_hints,
    "name-as-many": _name_as_many,
}


def _guess(rng: random.Random) -> str:
    return f"{rng.choice(_GUESS_WORDS)}{rng.randint(100, 9999)}"
