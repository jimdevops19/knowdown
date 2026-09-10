"""Loading ``resources/`` into the question tables.

The authoring loop this exists for: a question is written in YAML, reviewed in a
pull request, and loaded with ``manage.py sync_questions``. Everything here
follows from wanting that loop to be repeatable —

- **Upserts keyed on ``slug``**, so editing a question's wording and re-running
  corrects the row instead of inserting a second copy of the question beside it.
- **Nothing is deleted.** A question that disappears from the YAML is
  deactivated, because a matchup that already played it points at that row: a
  hard delete would edit a game two people have already finished.
- **Everything is validated before anything is written.** A typo in the last
  file must not leave the first half loaded, so parsing happens over every file
  first and the writes happen after, inside one transaction.

Child rows — options, accepted answers, headings, cells — are *replaced* rather
than upserted. They carry no history of their own (an answer records the option
id it chose, in ``apps.matches``, at the time it was chosen), and matching them
up across a reload would need a key nobody wants to author.
"""

from __future__ import annotations

import hashlib
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from django.conf import settings
from django.db import transaction

from apps.categories.models import Category
from apps.core_common.exceptions import ValidationFailed
# The question models themselves are reached through QUESTION_MODELS, not by
# name: this module must not grow an import per question type, or adding one
# would mean editing the loader in two places instead of the registry in one.
# The *child* models have no registry — each is written by exactly one branch of
# _write_children — so those are imported directly.
from apps.questions.models import (
    QUESTION_MODELS,
    FreeTextAnswer,
    ImageAnswerOption,
    MatrixCell,
    MatrixCellAnswer,
    MatrixColumn,
    MatrixKind,
    MatrixRow,
    MultipleAnswerOption,
    OrderingOption,
    QuestionType,
    SingleAnswerOption,
)
from apps.questions.rosters import load_rosters
from apps.questions.schemas import CategorySpec, QuestionFileSpec
from shared.logging import get_logger

logger = get_logger(__name__)

#: apps/questions/services/sync.py -> apps/questions/resources
RESOURCES = Path(__file__).resolve().parent.parent / "resources"
CATEGORIES_FILE = RESOURCES / "categories.yaml"

#: The folder inside a category's resource directory holding its binaries.
IMAGES_DIRNAME = "images"

#: Where copied images land under MEDIA_ROOT. Two trees, because a picture of
#: the play being asked about and a picture that *is* an answer option are shown
#: in different places and are worth being able to tell apart on disk.
QUESTION_IMAGE_DIR = "questions"
ANSWER_IMAGE_DIR = "questions/answers"


@dataclass
class LoadReport:
    """What a load did — for the command to print and the tests to assert on."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deactivated: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"{len(self.created)} created, {len(self.updated)} updated, "
            f"{len(self.deactivated)} deactivated"
        )


# --- Reading and parsing -----------------------------------------------------


def _read_yaml(path: Path):
    if not path.exists():
        raise ValidationFailed(f"Resource file not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def category_dirs(*, category: str | None = None) -> list[Path]:
    """The resource folders to load, one per category.

    ``category`` narrows it to a single folder — the usual case while authoring,
    where reloading every sport to check one question is just slower.
    """
    if category:
        path = RESOURCES / category
        if not path.is_dir():
            raise ValidationFailed(f"No resource folder for category '{category}'.")
        return [path]
    return sorted(
        child
        for child in RESOURCES.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    )


def _question_files(folder: Path) -> list[Path]:
    """Every YAML file in a category folder, in a stable order.

    Glob rather than a manifest: splitting ``single-answer.yaml`` into
    ``playoffs.yaml`` and ``finals.yaml`` should need no code change, and a file
    nobody listed is the classic way for a batch of questions to go missing.
    """
    return sorted(folder.glob("*.yaml"))


def _parse_files(folders: list[Path]) -> list[tuple[Path, QuestionFileSpec]]:
    """Validate every file before any of them is written.

    Problems are collected across all files rather than raised at the first one,
    so a reviewer fixing a batch of questions sees the whole list in one run.
    """
    parsed: list[tuple[Path, QuestionFileSpec]] = []
    problems: list[str] = []

    for folder in folders:
        files = _question_files(folder)
        if not files:
            problems.append(f"{folder.name}/: no .yaml files")
        for path in files:
            try:
                raw = _read_yaml(path)
            except ValidationFailed as exc:
                problems.append(str(exc.message))
                continue
            if not isinstance(raw, dict):
                problems.append(
                    f"{folder.name}/{path.name}: must be a mapping with "
                    "'category' and 'questions'"
                )
                continue
            try:
                spec = QuestionFileSpec.model_validate(raw)
            except Exception as exc:  # pydantic ValidationError, or a bad mapping
                problems.append(f"{folder.name}/{path.name}: {exc}")
                continue
            if spec.category != folder.name:
                # The folder is the category. A file claiming another one would
                # load questions into a sport nobody browsing that folder expects.
                problems.append(
                    f"{folder.name}/{path.name}: declares category "
                    f"{spec.category!r} but sits in {folder.name!r}"
                )
                continue
            parsed.append((path, spec))

    if problems:
        raise ValidationFailed("Invalid question resources.", details=problems)
    return parsed


def _reject_duplicate_slugs(parsed: list[tuple[Path, QuestionFileSpec]]) -> None:
    """Two entries claiming one slug would silently make the later file win.

    A slug is unique across *every* question table, not just within one: a played
    matchup records a question by (type, id), and a slug meaning two different
    questions is one nobody can name in a bug report. Nothing in the database can
    express that across seven tables, so it is checked here.
    """
    where: dict[str, list[str]] = {}
    for path, spec in parsed:
        for question in spec.questions:
            where.setdefault(question.slug, []).append(f"{path.parent.name}/{path.name}")

    clashes = [
        f"{slug!r} in {', '.join(files)}" for slug, files in where.items() if len(files) > 1
    ]
    if clashes:
        raise ValidationFailed("Duplicate question slugs.", details=sorted(clashes))


def _reject_slugs_taken_by_another_type(
    parsed: list[tuple[Path, QuestionFileSpec]],
) -> None:
    """The same check against what is already stored.

    Retyping a question — say a ``single-answer`` rewritten as ``multiple-answer``
    under the same slug — would otherwise insert a second row in a second table
    and leave the first behind, active. Refusing says so; the fix is a new slug,
    or deleting the old row deliberately.
    """
    wanted = {
        question.slug: str(question.type)
        for _, spec in parsed
        for question in spec.questions
    }
    problems: list[str] = []
    for question_type, model in QUESTION_MODELS.items():
        taken = model.all_objects.filter(slug__in=wanted).values_list("slug", flat=True)
        problems.extend(
            f"{slug!r} is already stored as {question_type}, the file says "
            f"{wanted[slug]}"
            for slug in taken
            if wanted[slug] != question_type
        )
    if problems:
        raise ValidationFailed(
            "Questions changing type under the same slug.", details=sorted(problems)
        )


# --- Images ------------------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_image(*, source: Path, relative_target: str) -> str:
    """Put a resource image under MEDIA_ROOT and answer with its stored path.

    Idempotent by content: a re-sync of an unchanged catalog copies no bytes,
    which is what makes running this on every deploy cheap. The comparison is a
    digest rather than an mtime because a git checkout rewrites mtimes and would
    make every file look new.
    """
    destination = Path(settings.MEDIA_ROOT) / relative_target
    if destination.exists() and _digest(destination) == _digest(source):
        return relative_target
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return relative_target


def _resolve_image(*, folder: Path, name: str, slug: str, field_name: str) -> Path:
    """Find an authored image, or refuse naming the question that wants it.

    A missing file has to fail the load: stored as a path to nothing it becomes a
    broken image in a live match, which is a question that cannot be answered.
    """
    source = folder / IMAGES_DIRNAME / name
    if not source.is_file():
        raise ValidationFailed(
            f"Question {slug!r}: {field_name} names {name!r}, which is not in "
            f"{folder.name}/{IMAGES_DIRNAME}/"
        )
    return source


# --- Writing -----------------------------------------------------------------


@transaction.atomic
def sync_categories(*, path: Path | None = None) -> LoadReport:
    """Upsert the categories from ``resources/categories.yaml``.

    Runs before the questions, which point at them. A category dropped from the
    file is deactivated rather than deleted — questions ``PROTECT`` it, and a
    sport being out of season is not the same as it never having existed.
    """
    source = path or CATEGORIES_FILE
    raw = _read_yaml(source)
    if not isinstance(raw, list):
        raise ValidationFailed(f"{source.name} must be a list of categories.")

    specs, problems = [], []
    for index, entry in enumerate(raw):
        try:
            specs.append(CategorySpec.model_validate(entry))
        except Exception as exc:
            slug = entry.get("slug", "?") if isinstance(entry, dict) else "?"
            problems.append(f"{source.name}[{index}] ({slug}): {exc}")
    if problems:
        raise ValidationFailed("Invalid categories.", details=problems)

    duplicates = [
        slug for slug, count in Counter(spec.slug for spec in specs).items() if count > 1
    ]
    if duplicates:
        raise ValidationFailed(f"Duplicate category slugs: {', '.join(sorted(duplicates))}")

    report = LoadReport()
    for spec in specs:
        _, created = Category.all_objects.update_or_create(
            slug=spec.slug,
            defaults={
                "name": spec.name,
                "description": spec.description,
                "is_active": spec.is_active,
                # A category that was soft-deleted and is back in the file is
                # being un-deleted, not duplicated: the unique index still holds
                # its slug, so the row has to be revived rather than inserted.
                "deleted_at": None,
            },
        )
        (report.created if created else report.updated).append(spec.slug)

    seen = {spec.slug for spec in specs}
    stale = Category.objects.filter(is_active=True).exclude(slug__in=seen)
    report.deactivated = sorted(stale.values_list("slug", flat=True))
    stale.update(is_active=False)

    logger.info("Categories synced", summary=str(report), file=source.name)
    return report


@transaction.atomic
def sync_questions(*, category: str | None = None) -> LoadReport:
    """Upsert every question under ``resources/<category>/*.yaml``.

    ``category`` narrows the load — and, importantly, narrows the *sweep* with
    it: loading one sport must not deactivate another's questions just because
    this run did not look at them.
    """
    folders = category_dirs(category=category)
    parsed = _parse_files(folders)
    _reject_duplicate_slugs(parsed)
    _reject_slugs_taken_by_another_type(parsed)

    categories = _categories_by_slug(parsed)

    report = LoadReport()
    for path, spec in parsed:
        folder = path.parent
        for question in spec.questions:
            created = _write_question(
                spec=question, category=categories[spec.category], folder=folder
            )
            (report.created if created else report.updated).append(question.slug)

    report.deactivated = _deactivate_missing(
        parsed=parsed, categories=list(categories.values())
    )

    logger.info(
        "Questions synced",
        summary=str(report),
        category=category or "all",
        count=len(report.created) + len(report.updated),
    )
    return report


def _categories_by_slug(
    parsed: list[tuple[Path, QuestionFileSpec]],
) -> dict[str, Category]:
    """Every category the files point at, or a refusal naming the missing ones.

    Questions are loaded *after* categories for this reason: a folder with no row
    behind it is a folder of questions nobody can be asked, and creating the
    category implicitly here would let a typo in a folder name invent a sport.
    """
    wanted = {spec.category for _, spec in parsed}
    found = {c.slug: c for c in Category.all_objects.filter(slug__in=wanted)}
    missing = wanted - found.keys()
    if missing:
        raise ValidationFailed(
            f"Unknown categories: {', '.join(sorted(missing))}. "
            "Add them to resources/categories.yaml first."
        )
    return found


def _write_question(*, spec, category: Category, folder: Path) -> bool:
    """Upsert one question and replace its children. Returns *created*."""
    model = QUESTION_MODELS[spec.type]
    defaults = {
        "description": spec.description,
        "category": category,
        "tags": spec.tags,
        "level": spec.level,
        "time_limit_seconds": spec.time_limit_seconds,
        "image": _question_image(spec=spec, folder=folder),
        "is_active": True,
        # Revive rather than insert beside it — see sync_categories.
        "deleted_at": None,
    }
    defaults.update(_type_specific_fields(spec))

    question, created = model.all_objects.update_or_create(
        slug=spec.slug, defaults=defaults
    )
    _write_children(spec=spec, question=question, folder=folder)
    return created


def _question_image(*, spec, folder: Path) -> str:
    """The stored path for a question's own illustration, or ``""``."""
    if not spec.image:
        return ""
    source = _resolve_image(
        folder=folder, name=spec.image, slug=spec.slug, field_name="image"
    )
    return _copy_image(
        source=source,
        relative_target=f"{QUESTION_IMAGE_DIR}/{folder.name}/{spec.image}",
    )


def _type_specific_fields(spec) -> dict:
    """The columns only one question type has."""
    if spec.type == QuestionType.TRUE_FALSE:
        return {"answer": spec.answer}
    if spec.type == QuestionType.ORDERING:
        return {"instruction": spec.instruction}
    if spec.type == QuestionType.MATRIX:
        # Derived from the headings, never authored: a count that can disagree
        # with the thing it counts eventually will.
        return {
            "row_count": len(spec.rows),
            "column_count": len(spec.columns),
            "kind": spec.kind,
        }
    return {}


def _write_children(*, spec, question, folder: Path) -> None:
    """Replace a question's options / answers / grid.

    Wholesale replacement, not a diff: nothing points at these rows across a
    reload (a recorded answer keeps the option id it chose at the time, in the
    match tables), and matching them up would need a per-option key nobody wants
    to author. ``order`` is the list order, so a resource file cannot have a gap.
    """
    if spec.type == QuestionType.SINGLE_ANSWER:
        question.options.all().delete()
        SingleAnswerOption.objects.bulk_create(
            SingleAnswerOption(
                question=question,
                text=option.text,
                is_correct=option.is_correct,
                order=index,
            )
            for index, option in enumerate(spec.options, start=1)
        )

    elif spec.type == QuestionType.IMAGE_ANSWER:
        question.options.all().delete()
        ImageAnswerOption.objects.bulk_create(
            ImageAnswerOption(
                question=question,
                image=_copy_image(
                    source=_resolve_image(
                        folder=folder,
                        name=option.image,
                        slug=spec.slug,
                        field_name="option image",
                    ),
                    relative_target=f"{ANSWER_IMAGE_DIR}/{folder.name}/{option.image}",
                ),
                label=option.label,
                is_correct=option.is_correct,
                order=index,
            )
            for index, option in enumerate(spec.options, start=1)
        )

    elif spec.type == QuestionType.MULTIPLE_ANSWER:
        question.options.all().delete()
        MultipleAnswerOption.objects.bulk_create(
            MultipleAnswerOption(
                question=question,
                text=option.text,
                is_correct=option.is_correct,
                order=index,
            )
            for index, option in enumerate(spec.options, start=1)
        )

    elif spec.type == QuestionType.FREE_TEXT:
        question.accepted_answers.all().delete()
        FreeTextAnswer.objects.bulk_create(
            FreeTextAnswer(question=question, value=value)
            for value in spec.accepted_answers
        )

    elif spec.type == QuestionType.ORDERING:
        question.options.all().delete()
        OrderingOption.objects.bulk_create(
            OrderingOption(question=question, text=text, correct_position=index)
            for index, text in enumerate(spec.items, start=1)
        )

    elif spec.type == QuestionType.MATRIX:
        # Cells cascade off the headings, so clearing those clears the grid.
        question.rows.all().delete()
        question.columns.all().delete()
        titles = _matrix_headings(spec)
        rows = {
            title: MatrixRow.objects.create(
                question=question, title=titles[title], order=index
            )
            for index, title in enumerate(spec.rows, start=1)
        }
        columns = {
            title: MatrixColumn.objects.create(
                question=question, title=titles[title], order=index
            )
            for index, title in enumerate(spec.columns, start=1)
        }

        if spec.kind == MatrixKind.TEAMS:
            _write_team_grid(spec=spec, question=question, rows=rows, columns=columns)
            return

        cells = MatrixCell.objects.bulk_create(
            MatrixCell(
                question=question,
                row=rows[cell.row],
                column=columns[cell.column],
            )
            for cell in spec.cells
        )
        # Zipped rather than looked up by (row, column): ``bulk_create`` returns
        # the rows in the order it was given them, which is the order of
        # ``spec.cells``, and the pairing is what the schema already checked is
        # unique.
        MatrixCellAnswer.objects.bulk_create(
            MatrixCellAnswer(
                cell=cell,
                value=answer.answer,
                probability_score=answer.probability_score,
            )
            for cell, spec_cell in zip(cells, spec.cells)
            for answer in spec_cell.answers
        )


def _matrix_headings(spec) -> dict[str, str]:
    """Each authored heading mapped to the title to store for it.

    Itself for an authored grid — the file says what the axis is called. For a
    ``kind: teams`` grid it is the roster artifact's spelling of the franchise,
    so a file that wrote ``los angeles lakers`` still puts *Los Angeles Lakers*
    on the board: the artifact is what decides who played for it, so it may as
    well decide what it is called. Only capitalisation and spacing can differ —
    a heading naming no franchise at all never gets this far (see
    ``schemas.MatrixSpec``).
    """
    authored = [*spec.rows, *spec.columns]
    if spec.kind != MatrixKind.TEAMS:
        return {title: title for title in authored}
    rosters = load_rosters()
    return {title: rosters.canonical_team(title) or title for title in authored}


def _write_team_grid(*, spec, question, rows: dict, columns: dict) -> None:
    """The cells of a ``kind: teams`` grid, derived from the roster artifact.

    Two rules, both of them the sparseness ``models.MatrixCell`` describes,
    decided from the data rather than by an author:

    - a pairing the two rosters never shared is **not written**, so a player is
      never given an input for a square nobody can fill;
    - a franchise against itself is not written either. Its answer is everybody
      who ever wore the shirt, which is not a question.

    No :class:`MatrixCellAnswer` rows are written at all. The answer key is the
    artifact, read at evaluation time (``services.evaluation``) — copying tens
    of thousands of names into the database per question would make every
    question that asks about the Lakers carry its own copy of the Lakers, and
    make re-baking the artifact a data migration.
    """
    rosters = load_rosters()
    MatrixCell.objects.bulk_create(
        MatrixCell(question=question, row=row, column=column)
        for row_title, row in rows.items()
        for column_title, column in columns.items()
        if row.title != column.title
        and rosters.players_for_all((row.title, column.title))
    )


def _deactivate_missing(
    *, parsed: list[tuple[Path, QuestionFileSpec]], categories: list[Category]
) -> list[str]:
    """Stand down every active question in these categories the files no longer
    hold.

    Scoped to the categories that were actually loaded, so ``--category nba``
    cannot quietly retire the whole F1 catalog. Deactivation, never deletion: the
    row is somebody's match history.
    """
    seen = {question.slug for _, spec in parsed for question in spec.questions}
    deactivated: list[str] = []
    for model in QUESTION_MODELS.values():
        stale = model.objects.filter(is_active=True, category__in=categories).exclude(
            slug__in=seen
        )
        deactivated.extend(stale.values_list("slug", flat=True))
        stale.update(is_active=False)
    return sorted(deactivated)


def load_resources(*, category: str | None = None) -> tuple[LoadReport, LoadReport]:
    """Categories first — every question points at one."""
    return sync_categories(), sync_questions(category=category)
