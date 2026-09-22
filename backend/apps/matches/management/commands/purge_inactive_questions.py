"""Hard-delete inactive questions, and the match rows that point at them.

    python manage.py purge_inactive_questions                      # dry run
    python manage.py purge_inactive_questions --no-dry-run         # one by one
    python manage.py purge_inactive_questions --no-dry-run --yes    # all of them
    python manage.py purge_inactive_questions --type image-answer --slug nba-x

**This is the one thing the platform otherwise refuses to do.**
``sync_questions`` deactivates a question dropped from the YAML rather than
deleting it, because a matchup that already played it points at its row and a
hard delete would edit a game two people have finished. That rule is right for
a question being *parked*; it has no answer for one that should never have
been written. This command is the deliberate exception, and it pays the price
the rule was protecting: a purged question's ``MatchupQuestion`` rows and the
``PlayerAnswer`` rows under them go with it, so a match that played it comes
back from ``GET /api/v1/matches/{id}/`` one question shorter.

**A row rather than a soft delete, and the debris with it.** A question row
holds its slug in a unique index whether it is soft-deleted or not, so
stamping ``deleted_at`` would leave the name taken and the next sync reviving
it. And a ``MatchupQuestion`` left behind is worse than untidy: it identifies
its question by ``(question_type, question_id)`` with no foreign key to stop
it, so a dangling pair is a match-history row that raises ``NotFound`` from
``apps.questions.selectors.get_question`` when somebody opens the box score.

**Dry run is the default**, the inverse of ``purge_stress``: that command
sweeps rows it created itself under a tag nothing else uses, this one is
pointed at the real catalog by hand. ``--no-dry-run`` without ``--yes`` asks
about every question one at a time, showing what each one takes with it.

**Frozen results are not recomputed.** ``Matchup.question_count`` stays the
length both players agreed to, the scores on ``MatchupPlayer`` stay what was
earned, and ratings and badges are untouched — those were decided once, at the
final whistle, and re-deriving them from a board that has since changed would
be a worse lie than a match that is one question short. The ``Matchup`` itself
is never deleted, even when every question it played is purged.

**Why this lives in ``apps.matches``.** It has to know both halves, and the
dependency runs one way: ``apps.matches`` reads ``apps.questions`` and
``apps.questions`` has never heard of a match. A question-side command would
have had to import the match engine to clean up after itself.

**Media is left alone.** An option's image file stays in ``MEDIA_ROOT``;
``sync_questions`` copies images by content digest, so an orphan costs disk
and nothing else, and deleting one that another question happens to share
would blank a live board.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.matches.models import MatchupQuestion, PlayerAnswer
from apps.questions.models import QUESTION_MODELS
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _Doomed:
    """One inactive question and everything that would go with it."""

    question_type: str
    question: object
    matchup_question_ids: list[int] = field(default_factory=list)
    matchup_ids: set = field(default_factory=set)
    answer_count: int = 0

    @property
    def slug(self) -> str:
        return self.question.slug

    def line(self) -> str:
        state = "soft-deleted" if self.question.is_deleted else "inactive"
        return (
            f"{self.slug}  [{self.question_type}, {state}, "
            f"level {self.question.level}, {self.question.category.slug}]"
        )

    def cost(self) -> str:
        return (
            f"{len(self.matchup_question_ids)} match question(s) in "
            f"{len(self.matchup_ids)} matchup(s), {self.answer_count} answer(s)"
        )


def collect_doomed(*, types=(), slugs=(), category=None) -> list[_Doomed]:
    """Every inactive question the filters allow, each with its debris.

    A soft-deleted row counts as inactive whatever its ``is_active`` says: it
    is unplayable and it is still holding its slug, which is the whole reason
    somebody would be running this.
    """
    doomed: list[_Doomed] = []
    for question_type, model in QUESTION_MODELS.items():
        if types and question_type not in types:
            continue
        questions = model.all_objects.filter(
            Q(is_active=False) | Q(deleted_at__isnull=False)
        ).select_related("category")
        if slugs:
            questions = questions.filter(slug__in=slugs)
        if category:
            questions = questions.filter(category__slug=category)
        for question in questions.order_by("slug"):
            entry = _Doomed(question_type=question_type, question=question)
            rows = MatchupQuestion.objects.filter(
                question_type=question_type, question_id=str(question.id)
            ).values_list("id", "matchup_id")
            entry.matchup_question_ids = [row[0] for row in rows]
            entry.matchup_ids = {row[1] for row in rows}
            entry.answer_count = PlayerAnswer.objects.filter(
                matchup_question_id__in=entry.matchup_question_ids
            ).count()
            doomed.append(entry)
    return doomed


def purge(entry: _Doomed) -> None:
    """Delete one question, leaf-first, for real.

    ``hard_delete``, because ``BaseQuestion`` is a ``BaseModel`` whose
    ``.delete()`` only stamps ``deleted_at`` — see this module's docstring for
    why that is not enough here. The question's own options, cells and accepted
    answers are plain ``CASCADE`` children and go with it.
    """
    with transaction.atomic():
        PlayerAnswer.objects.filter(
            matchup_question_id__in=entry.matchup_question_ids
        ).delete()
        MatchupQuestion.objects.filter(id__in=entry.matchup_question_ids).delete()
        type(entry.question).all_objects.filter(id=entry.question.id).hard_delete()


class Command(BaseCommand):
    help = (
        "Hard-delete inactive questions and the match rows pointing at them. "
        "Reports and writes nothing unless --no-dry-run is given."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-dry-run",
            action="store_true",
            dest="no_dry_run",
            help="Actually delete. Without it this only reports what it found.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Delete every question found without asking. Without it, "
            "--no-dry-run asks about each one in turn.",
        )
        parser.add_argument(
            "--type",
            action="append",
            dest="types",
            default=[],
            choices=sorted(QUESTION_MODELS),
            help="Only this question type. Repeatable.",
        )
        parser.add_argument(
            "--slug",
            action="append",
            dest="slugs",
            default=[],
            help="Only this question, by slug. Repeatable.",
        )
        parser.add_argument(
            "--category",
            help="Only questions in this category, by slug.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = not options["no_dry_run"]
        approve_all = options["yes"]

        doomed = collect_doomed(
            types=tuple(options["types"]),
            slugs=tuple(options["slugs"]),
            category=options["category"],
        )
        if not doomed:
            self.stdout.write("No inactive questions match. Nothing to purge.")
            return

        self.stdout.write(f"{len(doomed)} inactive question(s) found:")
        for entry in doomed:
            self.stdout.write(f"  {entry.line()}")
            self.stdout.write(f"      takes with it: {entry.cost()}")

        if dry_run:
            self.stdout.write(
                "Dry run — nothing was deleted. Re-run with --no-dry-run to "
                "approve each one, or --no-dry-run --yes to purge them all."
            )
            return

        if not approve_all and not sys.stdin.isatty():
            raise CommandError(
                "One-by-one approval needs a terminal to ask at. Pass --yes to "
                "purge everything listed above without being asked."
            )

        purged: list[_Doomed] = []
        for entry in doomed:
            if not approve_all:
                answer = self._ask(entry)
                if answer == "quit":
                    self.stdout.write("Stopped. Everything left is untouched.")
                    break
                if answer == "all":
                    approve_all = True
                elif answer == "no":
                    self.stdout.write(f"  kept {entry.slug}")
                    continue
            purge(entry)
            purged.append(entry)
            self.stdout.write(self.style.WARNING(f"  purged {entry.slug}"))

        if not purged:
            self.stdout.write("Nothing was deleted.")
            return

        matchups = set().union(*(entry.matchup_ids for entry in purged))
        answers = sum(entry.answer_count for entry in purged)
        rows = sum(len(entry.matchup_question_ids) for entry in purged)
        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {len(purged)} question(s), {rows} match question(s) "
                f"across {len(matchups)} matchup(s) and {answers} answer(s)."
            )
        )
        if matchups:
            self.stdout.write(
                "Those matchups are now one or more questions shorter than the "
                "length they were played at; scores, ratings and badges are as "
                "they were — see this command's docstring."
            )
        logger.info(
            "Inactive questions purged",
            count=len(purged),
            summary=", ".join(f"{entry.question_type}:{entry.slug}" for entry in purged),
        )

    def _ask(self, entry: _Doomed) -> str:
        """Approve one question. ``all`` approves the rest of the list too."""
        while True:
            self.stdout.write("")
            self.stdout.write(f"Purge {entry.line()}?")
            self.stdout.write(f"  it takes with it: {entry.cost()}")
            choice = input("  [y]es / [n]o / [a]ll / [q]uit: ").strip().lower()
            if choice in {"y", "yes"}:
                return "yes"
            if choice in {"n", "no", ""}:
                return "no"
            if choice in {"a", "all"}:
                return "all"
            if choice in {"q", "quit"}:
                return "quit"
            self.stdout.write("  Answer y, n, a or q.")
