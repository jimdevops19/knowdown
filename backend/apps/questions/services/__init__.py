"""The write side of the questions domain.

Two things: ``sync`` loads the resource files — which are how questions come
into being, so there is deliberately no service that creates one from a request
payload — and ``evaluation`` says whether a submitted answer is right.

Evaluation lives here rather than in ``apps.matches`` for the same reason
selection lives in ``apps.questions.selectors``: the match engine must stay
independent of the seven answer shapes, so "is this answer correct?" is a
question this domain answers and the match domain merely asks. It is the seam
that keeps the match engine from ever learning what a correct answer looks like.
"""

from __future__ import annotations

from apps.questions.services.evaluation import (
    ANSWER_EVALUATORS,
    AnswerResult,
    evaluate_answer,
    parse_submission,
)
from apps.questions.services.sync import (
    LoadReport,
    load_resources,
    sync_categories,
    sync_questions,
)

__all__ = [
    "ANSWER_EVALUATORS",
    "AnswerResult",
    "LoadReport",
    "evaluate_answer",
    "load_resources",
    "parse_submission",
    "sync_categories",
    "sync_questions",
]
