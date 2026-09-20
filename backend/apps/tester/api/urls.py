"""The tester's routes, mounted at ``/api/v1/tester/`` by ``config/urls.py``
only where ``TESTER_ENDPOINT_ENABLED`` is on.

A question is named the way it is named everywhere else in this platform — by
the ``(type, id)`` pair ``selectors.QuestionRef`` stands for — rather than by
slug, even though the slug is the readable name and this surface is the one
place that publishes it. Two reasons: a slug is unique across the catalog only
by the loader's own check, while ``(type, id)`` is unique by construction, and
the id is what the client already holds after listing the catalog.
"""

from django.urls import path

from .views import (
    AnswerAttemptView,
    AnswerKeyView,
    CatalogListView,
    QuestionSourceView,
    RehearsalView,
    TesterConfigView,
)

app_name = "tester"

# `str` rather than `slug` for the type: the QuestionType values contain
# hyphens, which `slug` accepts, but they are an enum and not a slug — an
# unknown value belongs to `get_question`'s 404, which names what was wrong,
# rather than to a URL resolver that would 404 with nothing to say.
_QUESTION = "questions/<str:question_type>/<uuid:question_id>/"

urlpatterns = [
    path("config/", TesterConfigView.as_view(), name="config"),
    path("questions/", CatalogListView.as_view(), name="question-list"),
    path(_QUESTION, RehearsalView.as_view(), name="question-rehearsal"),
    path(f"{_QUESTION}answer/", AnswerAttemptView.as_view(), name="question-answer"),
    path(f"{_QUESTION}answer-key/", AnswerKeyView.as_view(), name="question-answer-key"),
    # The authored YAML behind a question — read it, replace it, or retire it.
    # `source` rather than hanging the write verbs off the rehearsal URL above:
    # what these three edit is the block in the resource file, and the row
    # changing is a consequence of the load that follows, not the request.
    path(f"{_QUESTION}source/", QuestionSourceView.as_view(), name="question-source"),
]
