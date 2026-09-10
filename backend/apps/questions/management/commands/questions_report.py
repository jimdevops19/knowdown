"""What the catalog holds, and whether it is enough to play.

    uv run python manage.py questions_report
    uv run python manage.py questions_report --category nba
    uv run python manage.py questions_report --count 5
    uv run python manage.py questions_report --include-inactive

Two tables and a verdict. The verdict is the point: a category whose level band
holds fewer questions than the longest match needs is a category where
matchmaking *refuses* (``selectors.select_questions``), so this command exits
non-zero on it — which is what lets a deploy pipeline find out before two
players do.

The counterpart to ``sync_questions``: that one puts questions in, this one says
what is in there. Both are read from the same place a match is (only active
questions in active categories), so the number printed here is the number the
matchmaker will find.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.categories.models import Category
from apps.questions.constants import CATALOG_DEPTH_TARGET, LONGEST_MATCH_QUESTION_COUNT
from apps.questions.models import QUESTION_MODELS
from apps.questions.selectors import CategoryDepth, catalog_depth

#: Short headings for the per-type table — ``single-answer`` and friends are the
#: authored keys and are too wide to tile seven across a terminal.
TYPE_HEADINGS = {
    "single-answer": "single",
    "image-answer": "image",
    "multiple-answer": "multi",
    "true-false": "t/f",
    "free-text": "text",
    "ordering": "order",
    "matrix": "matrix",
}


class Command(BaseCommand):
    help = "Report the question catalog's depth per category, type and level band."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--category",
            metavar="SLUG",
            help="Report on one category rather than every active one.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=LONGEST_MATCH_QUESTION_COUNT,
            metavar="N",
            help=(
                "The match length a band must be able to fill "
                f"(default {LONGEST_MATCH_QUESTION_COUNT}, the longest match)."
            ),
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help=(
                "Count categories that are switched off too. They cannot be "
                "played, so they are excluded by default and never fail the "
                "command — this is for seeing a sport that is still being "
                "authored."
            ),
        )

    def handle(self, *args, **options) -> None:
        count = options["count"]
        if count < 1:
            raise CommandError("--count must be at least 1.")

        depths = catalog_depth(categories=self._categories(options))
        if not depths:
            raise CommandError("No categories to report on.")

        self._depth_table(depths, count=count)
        self._type_table(depths)

        # Only active categories can fail the command: an inactive one is out of
        # service by choice, and being thin is why.
        thin = [
            (depth, depth.thin_bands(count=count))
            for depth in depths
            if depth.category.is_active
        ]
        thin = [(depth, bands) for depth, bands in thin if bands]
        if thin:
            self._report_thin(thin, count=count)
            raise CommandError(
                f"{len(thin)} active categor{'y' if len(thin) == 1 else 'ies'} "
                f"cannot fill a {count}-question match at every level band."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Every active category can fill a {count}-question match at every "
                f"level band."
            )
        )

    # --- Reads ---------------------------------------------------------------

    def _categories(self, options) -> list[Category] | None:
        """The categories to report on, or ``None`` to let the selector pick.

        ``None`` rather than a list of every active category, so "which
        categories count" stays one decision, made in the selector, where the
        matchmaker will read it from too.
        """
        if options["category"]:
            category = Category.objects.filter(slug=options["category"]).first()
            if category is None:
                raise CommandError(f"No category with slug '{options['category']}'.")
            return [category]
        if options["include_inactive"]:
            return list(Category.objects.all())
        return None

    # --- Tables --------------------------------------------------------------

    def _depth_table(self, depths: list[CategoryDepth], *, count: int) -> None:
        """Depth per band: the table the exit code is decided from.

        ``to target`` is a content gap, not a fault — see
        ``constants.CATALOG_DEPTH_TARGET``: ``count`` questions makes a band
        playable, and the target is where it stops being the same board every
        time.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("Depth by level band"))
        self._row(("category", "band", "levels", "questions", "playable", "to target"))
        self._rule()

        for depth in depths:
            for band in depth.bands:
                playable = band.playable(count=count)
                shortfall = max(0, CATALOG_DEPTH_TARGET - band.total)
                self._row(
                    (
                        depth.category.slug
                        + ("" if depth.category.is_active else " (off)"),
                        band.band.name,
                        str(band.band),
                        str(band.total),
                        "yes" if playable else f"NO (needs {count})",
                        "—" if not shortfall else f"+{shortfall}",
                    ),
                    style=None if playable else self.style.ERROR,
                )
            self._row((depth.category.slug, "all", "1-10", str(depth.total), "", ""))
        self.stdout.write("")

    def _type_table(self, depths: list[CategoryDepth]) -> None:
        """Depth per question type.

        Separate from the band table rather than a wider version of it: seven
        types across three bands is 21 numbers per category, which is a matrix
        nobody reads. This answers a different question — "does the catalog
        exercise every answer shape, or is it four hundred single-answers?" —
        and a type sitting at zero is a client feature nobody is testing.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("Depth by question type"))
        headings = [TYPE_HEADINGS.get(key, key) for key in QUESTION_MODELS]
        self._row(("category", *headings), widths=self._type_widths())
        self._rule()

        for depth in depths:
            by_type = depth.by_type
            self._row(
                (
                    depth.category.slug,
                    *(str(by_type[question_type]) for question_type in QUESTION_MODELS),
                ),
                widths=self._type_widths(),
            )
        self.stdout.write("")

    def _report_thin(self, thin: list, *, count: int) -> None:
        for depth, bands in thin:
            for band in bands:
                self.stderr.write(
                    f"  {depth.category.slug} band {band.band.name} "
                    f"({band.band}) holds {band.total} of the {count} questions a "
                    f"match needs"
                )

    # --- Printing ------------------------------------------------------------

    #: Column widths for the band table, in order.
    WIDTHS = (14, 8, 8, 11, 20, 10)

    def _type_widths(self) -> tuple[int, ...]:
        return (14, *(8 for _ in QUESTION_MODELS))

    def _row(self, cells, *, widths: tuple[int, ...] | None = None, style=None) -> None:
        line = "".join(
            str(cell).ljust(width)
            for cell, width in zip(cells, widths or self.WIDTHS)
        ).rstrip()
        self.stdout.write(style(line) if style else line)

    def _rule(self) -> None:
        self.stdout.write("-" * 70)
