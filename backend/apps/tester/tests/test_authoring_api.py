"""The tester's write endpoints, over HTTP.

``apps.questions.tests.test_authoring`` is where the file-and-load behaviour is
pinned down; this is about the surface in front of it — that the same two gates
hold on the three verbs that *write* (which is the pair that matters most, since
these edit the repository), that a create goes in by ``POST`` and comes back
with both halves of what happened, and that the edit form is seeded from the
file rather than from the row.

The resources tree is temporary and written by the test, for the reason
``test_sync`` gives: these tests write to whatever they are pointed at, and the
shipped catalog is not a fixture.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from rest_framework.test import APITestCase

from apps.categories.models import Category
from apps.questions.models import SingleAnswerQuestion
from apps.questions.services import sync
from apps.tester.tests.test_api import (
    client_for,
    make_maintainer,
    make_ordinary_player,
)

FILE = """\
# NBA — single-answer questions.

category: nba

time_limit_seconds: 10

questions:
  - type: single-answer
    slug: who-scored
    description: Who won it?
    level: 3
    options:
      - text: Boston Celtics
        is_correct: true
      - text: Los Angeles Lakers
"""

NEW_ENTRY = {
    "type": "single-answer",
    "slug": "a-fresh-one",
    "description": "Who else won it?",
    "level": 4,
    "tags": {"topic": "teams"},
    "options": [
        {"text": "Chicago Bulls", "is_correct": True},
        {"text": "Detroit Pistons"},
    ],
}


class AuthoringAPITestCase(APITestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # The loader — and the authoring service through it — resolves the tree
        # off these two module attributes, so pointing them at a temporary
        # folder is all a test tree takes.
        self._real = (sync.RESOURCES, sync.CATEGORIES_FILE)
        sync.RESOURCES = self.root
        sync.CATEGORIES_FILE = self.root / "categories.yaml"
        self.addCleanup(self._restore)

        (self.root / "categories.yaml").write_text(
            yaml.safe_dump([{"slug": "nba", "name": "NBA"}])
        )
        folder = self.root / "nba"
        folder.mkdir()
        self.path = folder / "single-answer.yaml"
        self.path.write_text(FILE, encoding="utf-8")

        sync.sync_categories()
        sync.sync_questions()
        self.question = SingleAnswerQuestion.objects.get(slug="who-scored")
        self.staff = make_maintainer()
        self.client = client_for(self.staff)

    def _restore(self):
        sync.RESOURCES, sync.CATEGORIES_FILE = self._real

    @property
    def source_url(self) -> str:
        return f"/api/v1/tester/questions/single-answer/{self.question.id}/source/"

    def entries(self) -> list[dict]:
        return yaml.safe_load(self.path.read_text(encoding="utf-8"))["questions"]


class DoorTests(AuthoringAPITestCase):
    """The write verbs are gated exactly as the read ones are.

    Worth its own test rather than an extension of the existing door suite:
    these three edit files in the repository, so a gap here is a gap that lets
    a signed-in stranger author questions into the catalog.
    """

    def test_an_anonymous_caller_cannot_write(self):
        anonymous = client_for(None)
        self.assertEqual(
            anonymous.post(
                "/api/v1/tester/questions/",
                {"category": "nba", "entry": NEW_ENTRY},
                format="json",
            ).status_code,
            401,
        )
        self.assertEqual(anonymous.get(self.source_url).status_code, 401)
        self.assertEqual(
            anonymous.patch(self.source_url, {"is_active": False}, format="json").status_code,
            401,
        )

    def test_a_signed_in_player_who_is_not_staff_cannot_write(self):
        player = client_for(make_ordinary_player())
        self.assertEqual(
            player.post(
                "/api/v1/tester/questions/",
                {"category": "nba", "entry": NEW_ENTRY},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            player.put(self.source_url, {"entry": NEW_ENTRY}, format="json").status_code,
            403,
        )
        self.assertEqual(
            player.patch(self.source_url, {"is_active": False}, format="json").status_code,
            403,
        )
        # And the refusal is a refusal, not a refusal after the fact.
        self.assertEqual([entry["slug"] for entry in self.entries()], ["who-scored"])


class CreateTests(AuthoringAPITestCase):
    def test_a_create_writes_the_file_and_reports_both_halves(self):
        response = self.client.post(
            "/api/v1/tester/questions/",
            {"category": "nba", "entry": NEW_ENTRY},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()["data"]
        self.assertEqual(body["action"], "created")
        self.assertEqual(body["source"]["path"], "nba/single-answer.yaml")
        self.assertEqual(body["question"]["slug"], "a-fresh-one")
        self.assertEqual(body["question"]["level"], 4)
        # The load that followed, in the loader's own words.
        self.assertEqual(body["sync"]["created"], ["a-fresh-one"])
        self.assertEqual(body["sync"]["summary"], "1 created, 1 updated, 0 deactivated")

        self.assertEqual(
            [entry["slug"] for entry in self.entries()], ["who-scored", "a-fresh-one"]
        )
        self.assertTrue(SingleAnswerQuestion.objects.filter(slug="a-fresh-one").exists())

    def test_an_invalid_entry_is_a_400_and_changes_nothing(self):
        response = self.client.post(
            "/api/v1/tester/questions/",
            {
                "category": "nba",
                "entry": {**NEW_ENTRY, "options": [{"text": "Only one", "is_correct": True}]},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual([entry["slug"] for entry in self.entries()], ["who-scored"])
        self.assertFalse(SingleAnswerQuestion.objects.filter(slug="a-fresh-one").exists())

    def test_an_unknown_category_is_refused(self):
        response = self.client.post(
            "/api/v1/tester/questions/",
            {"category": "nothing-like-it", "entry": NEW_ENTRY},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class ReadAndUpdateTests(AuthoringAPITestCase):
    def test_the_source_endpoint_answers_with_the_authored_entry(self):
        body = self.client.get(self.source_url).json()["data"]

        self.assertEqual(body["path"], "nba/single-answer.yaml")
        self.assertEqual(body["category"], "nba")
        self.assertEqual(body["entry"]["slug"], "who-scored")
        self.assertEqual(len(body["entry"]["options"]), 2)
        # The row carries the file's 10 seconds; the entry never named one, and
        # a form seeded from the row would send it back as an override.
        self.assertEqual(self.question.time_limit_seconds, 10)
        self.assertNotIn("time_limit_seconds", body["entry"])

    def test_a_put_replaces_the_block_and_reloads_the_row(self):
        entry = self.client.get(self.source_url).json()["data"]["entry"]

        response = self.client.put(
            self.source_url,
            {"entry": {**entry, "description": "Who really won it?", "level": 8}},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["action"], "updated")
        self.question.refresh_from_db()
        self.assertEqual(self.question.description, "Who really won it?")
        self.assertEqual(self.question.level, 8)
        self.assertIn(
            "description: Who really won it?", self.path.read_text(encoding="utf-8")
        )
        # The header comment is still there — the edit was one block, not a
        # re-dump of the document.
        self.assertIn("# NBA — single-answer questions.", self.path.read_text("utf-8"))

    def test_a_patch_retires_a_question_in_the_file_and_in_the_row(self):
        response = self.client.patch(
            self.source_url, {"is_active": False}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["data"]["question"]["is_active"], False)
        self.assertIn("is_active: false", self.path.read_text(encoding="utf-8"))
        self.question.refresh_from_db()
        self.assertFalse(self.question.is_active)

        # And it stays retired: the next deploy's sync reads the same file.
        sync.sync_questions()
        self.question.refresh_from_db()
        self.assertFalse(self.question.is_active)

    def test_a_patch_can_bring_one_back(self):
        self.client.patch(self.source_url, {"is_active": False}, format="json")
        self.client.patch(self.source_url, {"is_active": True}, format="json")

        self.question.refresh_from_db()
        self.assertTrue(self.question.is_active)
        self.assertNotIn("is_active", self.path.read_text(encoding="utf-8"))

    def test_a_question_whose_row_has_no_file_behind_it_is_a_400(self):
        """A row the resources no longer hold is a broken edit, not a 500."""
        orphan = SingleAnswerQuestion.objects.create(
            slug="hand-written",
            description="Typed straight into the database.",
            level=2,
            category=Category.objects.get(slug="nba"),
        )
        response = self.client.get(
            f"/api/v1/tester/questions/single-answer/{orphan.id}/source/"
        )
        self.assertEqual(response.status_code, 400)
