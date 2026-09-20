"""Editing the resource files, from something other than a text editor.

``services/sync.py`` is the *read* half of the authoring loop: YAML in, rows
out. This is the write half — the one the tester's CRUD surface calls — and its
whole job is to keep that loop's direction intact.

**The YAML stays the source of truth.** Nothing here writes a question row. A
create, an update or a deactivation is an edit to a file under ``resources/``,
followed by the ordinary ``sync_questions`` over that category — the same
function ``manage.py sync_questions`` runs and the same one a deploy runs. So a
question added from the tester is a question added *to the repository*: it
survives the next sync, it shows up in ``git diff``, and it is reviewable as the
text its author would have typed. The alternative — writing the row and then
best-effort appending to the file — has exactly one failure mode, and it is the
one that matters: the two disagree, and the next sync silently undoes the edit.

**One write, two effects, and the file goes first.** The order is: splice the
new text, validate it on its own, write it to disk, sync. A sync that refuses
rolls its transaction back *and* the file is restored from the copy taken before
the write, so a rejected edit leaves neither half changed. The file is written
before the sync rather than after because the sync is what reads it — there is
no way to ask the loader "would this parse" other than putting it where the
loader looks.

**Edits are surgical.** The blocks around the one being changed are not
re-emitted, so the long explanatory headers these files carry (and the comments
between entries, which are the closest thing the catalog has to review notes)
survive an edit made from a browser. That is why this module splices lines
rather than round-tripping the document through a YAML dumper, which would
reformat all hundred entries to change one word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apps.core_common.exceptions import ValidationFailed
from apps.questions.models import QUESTION_MODELS, QuestionType
from apps.questions.schemas import QuestionFileSpec
# The module, not its names: `sync.RESOURCES` is a rebindable module attribute
# (the loader's tests point it at a temporary tree), and importing the value
# here would take a copy that no longer moves with it.
from apps.questions.services import sync
from apps.questions.services.sync import LoadReport
from shared.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "AuthoredEntry",
    "SaveResult",
    "delete_entry",
    "read_entry",
    "save_entry",
    "set_entry_active",
]

#: The order keys are written in. Not alphabetical and not the order the client
#: happened to send: an entry is read by a human in a pull request, and the
#: shape of one — what it is, what it is called, what it asks — should not
#: depend on which form field was filled in first. Keys not named here follow,
#: in the order given, so a new key on a spec is a missing line here rather than
#: a dropped field.
FIELD_ORDER = (
    "type",
    "slug",
    "description",
    "level",
    "tags",
    "image",
    "time_limit_seconds",
    "pre_question_info",
    "is_active",
    # single/multiple/image-answer
    "options",
    # true-false
    "answer",
    # free-text
    "accepted_answers",
    # ordering
    "instruction",
    "items",
    # gradual-hints
    "hints",
    "hint_interval_seconds",
    "answer_fields",
    # matrix
    "kind",
    "rows",
    "columns",
    "cells",
    # name-as-many
    "dataset",
    "stat",
    "comparison",
    "threshold",
    "target_score",
)

#: Written when a category has no file for a type yet. Deliberately terse — the
#: hand-written files carry a page of format notes each, and a generated stub
#: pretending to be one of those would be a page of prose nobody wrote.
_NEW_FILE_TEMPLATE = """\
# {category} — {label} questions.
#
# Created by the question tester. Loaded by:
#   uv run python manage.py sync_questions --category {category}

category: {category}

questions:
"""


@dataclass(frozen=True)
class AuthoredEntry:
    """One question as its file has it — the form's starting point.

    Read from the YAML rather than rebuilt from the row, and the difference is
    the point: the row has lost whichever of the two clock tiers it came from
    (``sync`` resolves the file's ``time_limit_seconds`` into every entry), and
    an edit form seeded from it would hand every question an override it never
    asked for. What the file says is what the author typed.
    """

    #: Relative to ``resources/`` — ``nba/single-answer.yaml``. The thing to
    #: quote back to whoever made the edit, since it names the file to look at
    #: in the diff.
    path: str
    category: str
    entry: dict[str, Any]


@dataclass(frozen=True)
class SaveResult:
    """What an edit did, to the file and to the database.

    Both halves are reported because both happened, and a caller that showed
    only the row would be hiding the more surprising one. ``report`` is the
    loader's own summary, so "1 updated" here means the same thing it means in
    ``manage.py sync_questions`` output.
    """

    source: AuthoredEntry
    #: ``"created"`` or ``"updated"`` — about the *file*, not the row. They
    #: agree except when a question exists in the database and not in any file,
    #: which is a catalog somebody has been editing by hand.
    action: str
    report: LoadReport


# --- Locating ----------------------------------------------------------------


def _category_folder(category: str) -> Path:
    folder = sync.RESOURCES / category
    # Resolved and re-checked rather than trusted: `category` reaches here from
    # a request body, and `../../etc` is a category slug as far as a string is
    # concerned. The slug pattern on CategorySpec would refuse it too, but this
    # function is the one that turns a string into a filesystem path, so it is
    # the one that has to be sure.
    if not folder.resolve().is_relative_to(sync.RESOURCES.resolve()):
        raise ValidationFailed(f"Invalid category {category!r}.")
    return folder


def _question_files(folder: Path) -> list[Path]:
    """Every YAML in a category folder, manifest excluded.

    Deliberately *not* ``sync._question_files``: that one reads ``_active.yaml``
    and returns only what the category loads. A question parked in a file the
    manifest has commented out is still a question somebody may need to find and
    edit — and refusing to find it would make "where did my question go" a
    mystery rather than an answer.
    """
    return sorted(path for path in folder.glob("*.yaml") if path.name != sync.ACTIVE_FILE)


def _find_block(*, folder: Path, slug: str) -> tuple[Path, _Block] | None:
    """The file and line span holding ``slug``, or nothing."""
    for path in _question_files(folder):
        text = path.read_text(encoding="utf-8")
        for block in _blocks(text):
            if block.slug == slug:
                return path, block
    return None


def _target_file(*, folder: Path, question_type: str) -> Path:
    """Where a question of this type belongs: ``<category>/<type>.yaml``.

    The convention every existing folder already follows — a file is a file of
    one answer shape, which is what lets its header explain that shape once and
    its ``time_limit_seconds`` set the tempo for all of it
    (``schemas.QuestionFileSpec``). A create that invented its own filename
    would put a question somewhere no author would look for it.
    """
    return folder / f"{question_type}.yaml"


# --- Reading the file as blocks ----------------------------------------------


@dataclass(frozen=True)
class _Block:
    """One entry's span in a file, in line numbers.

    ``end`` excludes the trailing blank and comment lines that sit between this
    entry and the next: a comment there almost always introduces what follows,
    so replacing an entry must leave it where it is rather than carry it off
    with the text being replaced.
    """

    slug: str
    start: int
    end: int


#: A list item at exactly the indent the `questions:` list uses. Anchored to the
#: captured indent so that the nested lists inside an entry (`options:`,
#: `cells:`) — which are indented further — are not read as new entries.
def _item_pattern(indent: str) -> re.Pattern[str]:
    return re.compile(rf"^{indent}-\s")


def _questions_line(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if re.match(r"^questions:\s*(#.*)?$", line):
            return index
    raise ValidationFailed(
        "Resource file has no top-level 'questions:' list to edit."
    )


def _blocks(text: str) -> list[_Block]:
    """Every entry in a file, by slug and line span.

    The slug is taken by parsing each block on its own rather than by matching a
    ``slug:`` line, so an entry whose description happens to contain the word is
    not mistaken for one — and so a block that will not parse at all is skipped
    here and reported by the loader, which has the vocabulary for it.
    """
    lines = text.splitlines(keepends=True)
    try:
        head = _questions_line(lines)
    except ValidationFailed:
        return []

    indent = None
    starts: list[int] = []
    for index in range(head + 1, len(lines)):
        line = lines[index]
        if indent is None:
            match = re.match(r"^(\s*)-\s", line)
            if match:
                indent = match.group(1)
                starts.append(index)
            continue
        if _item_pattern(indent).match(line):
            starts.append(index)

    blocks: list[_Block] = []
    for position, start in enumerate(starts):
        limit = starts[position + 1] if position + 1 < len(starts) else len(lines)
        end = limit
        # Give back the blank lines and comments that introduce the next entry.
        while end > start + 1 and _is_gap(lines[end - 1]):
            end -= 1
        parsed = _parse_block("".join(lines[start:end]))
        if isinstance(parsed, dict) and isinstance(parsed.get("slug"), str):
            blocks.append(_Block(slug=parsed["slug"], start=start, end=end))
    return blocks


def _is_gap(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _parse_block(chunk: str):
    """One entry's lines as a mapping, or ``None`` if they do not parse."""
    try:
        loaded = yaml.safe_load(chunk)
    except yaml.YAMLError:
        return None
    return loaded[0] if isinstance(loaded, list) and len(loaded) == 1 else None


# --- Rendering ---------------------------------------------------------------


class _Flow(dict):
    """A mapping to emit inline — ``{topic: teams, era: all-time}``.

    Only ``tags`` uses it, and only because every file already writes tags that
    way: a three-key facet map exploded over four lines is the one place block
    style makes these files harder to scan rather than easier.
    """


class _Dumper(yaml.SafeDumper):
    """PyYAML's dumper, made to indent a list under the key that owns it.

    The default emits ``items:`` and then its entries at the *same* column,
    which is legal YAML and reads as a list belonging to nothing. Every
    hand-written resource file indents them, so a machine-written entry that
    did not would announce itself as machine-written in the diff.
    """

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


_Dumper.add_representer(
    _Flow,
    lambda dumper, data: dumper.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=True
    ),
)


def _normalised(entry: dict[str, Any]) -> dict[str, Any]:
    """The entry as it should appear in the file.

    Two rules, both about not writing down what the file already means. ``None``
    is dropped, because a key whose value is "unset" is the key being absent —
    and for ``time_limit_seconds`` and ``pre_question_info`` the absence is
    *meaningful*, since it is what hands the decision to the file's own line.
    ``is_active: true`` is dropped for the same reason: it is what every other
    entry says by saying nothing, and only ``false`` is worth a reader's
    attention.
    """
    cleaned = {
        key: value
        for key, value in entry.items()
        if value is not None and not (key == "is_active" and value is True)
    }
    if isinstance(cleaned.get("tags"), dict):
        if cleaned["tags"]:
            cleaned["tags"] = _Flow(cleaned["tags"])
        else:
            del cleaned["tags"]
    ordered = {key: cleaned.pop(key) for key in FIELD_ORDER if key in cleaned}
    ordered.update(cleaned)
    return ordered


def _render(entry: dict[str, Any], *, indent: str = "  ") -> str:
    """One entry as the lines a list item is made of.

    ``width`` is set high enough that the dumper never folds a line: a question
    wrapped mid-sentence across three lines is valid YAML and unreadable in a
    diff, which is where these are read.
    """
    body = yaml.dump(
        _normalised(entry),
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10_000,
    )
    lines = body.splitlines()
    rendered = [f"{indent}- {lines[0]}\n"]
    rendered += [f"{indent}  {line}\n" if line else "\n" for line in lines[1:]]
    return "".join(rendered)


# --- Splicing ----------------------------------------------------------------


def _with_entry(text: str, entry: dict[str, Any]) -> str:
    """``text`` with this entry's block replaced, or appended if it is new."""
    lines = text.splitlines(keepends=True)
    head = _questions_line(lines)
    indent = _list_indent(lines, head)
    rendered = _render(entry, indent=indent)

    for block in _blocks(text):
        if block.slug == entry["slug"]:
            return "".join(lines[: block.start]) + rendered + "".join(lines[block.end :])

    # Appended at the end of the list rather than sorted in. The order of a
    # resource file is its author's running order, and a new question has not
    # earned a place in the middle of one.
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "".join(lines) + rendered


def _without_entry(text: str, slug: str) -> str:
    lines = text.splitlines(keepends=True)
    for block in _blocks(text):
        if block.slug == slug:
            return "".join(lines[: block.start]) + "".join(lines[block.end :])
    return text


def _list_indent(lines: list[str], head: int) -> str:
    """The indent the file's existing entries use, or two spaces."""
    for line in lines[head + 1 :]:
        match = re.match(r"^(\s*)-\s", line)
        if match:
            return match.group(1)
    return "  "


# --- Writing -----------------------------------------------------------------


def _validate(*, path: Path, text: str, category: str) -> None:
    """Parse the whole spliced file before it is allowed near the disk.

    Redundant — the sync that follows parses it again, and would refuse the same
    file. It runs anyway because *this* error message can name the field the
    form got wrong while the file on disk is still the one that worked, and an
    error raised before a write is one that cannot half-happen.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationFailed(f"{path.name}: not valid YAML after the edit: {exc}")
    if not isinstance(raw, dict):
        raise ValidationFailed(f"{path.name}: must be a mapping.")
    if raw.get("category") != category:
        raise ValidationFailed(
            f"{path.name}: declares category {raw.get('category')!r}, expected {category!r}."
        )
    try:
        QuestionFileSpec.model_validate(raw)
    except Exception as exc:
        raise ValidationFailed(f"{path.name}: {exc}")


def _reject_slug_taken_elsewhere(*, slug: str, path: Path) -> None:
    """A slug is unique across the whole catalog, not just one file.

    The loader checks this too, but only over the files one sync reads — a
    ``--category nba`` run never opens the F1 folder. A create from the tester
    is exactly the moment somebody picks a name without knowing what is already
    taken, so the check here is over every category's files.
    """
    for other in sorted(sync.RESOURCES.iterdir()):
        if not other.is_dir() or other.name.startswith("."):
            continue
        for candidate in _question_files(other):
            if candidate == path:
                continue
            if any(block.slug == slug for block in _blocks(candidate.read_text("utf-8"))):
                raise ValidationFailed(
                    f"The slug {slug!r} is already used by "
                    f"{candidate.parent.name}/{candidate.name}."
                )


def _ensure_file(*, folder: Path, question_type: str, category: str) -> Path:
    """The file for this type, created — and listed in the manifest — if absent.

    The manifest half is not optional. ``_active.yaml`` is what a category
    loads, so a new file that is not named in it is a file of questions the
    loader never opens: the create would appear to work, write real YAML, and
    put nothing in the database.
    """
    path = _target_file(folder=folder, question_type=question_type)
    if path.exists():
        return path
    if not folder.is_dir():
        raise ValidationFailed(f"No resource folder for category '{category}'.")

    path.write_text(
        _NEW_FILE_TEMPLATE.format(
            category=category, label=str(QuestionType(question_type).label).lower()
        ),
        encoding="utf-8",
    )
    _add_to_manifest(folder=folder, name=path.name)
    return path


def _add_to_manifest(*, folder: Path, name: str) -> None:
    manifest = folder / sync.ACTIVE_FILE
    if not manifest.is_file():
        # No manifest means the folder loads every `*.yaml` in it, so the new
        # file is already loaded and inventing a manifest here would park every
        # file this one does not happen to list.
        return
    text = manifest.read_text(encoding="utf-8")
    if re.search(rf"^\s*-\s+{re.escape(name)}\s*$", text, re.MULTILINE):
        return
    if not text.endswith("\n"):
        text += "\n"
    manifest.write_text(f"{text}  - {name}\n", encoding="utf-8")


def _remove_from_manifest(*, folder: Path, name: str) -> None:
    """Undo :func:`_add_to_manifest`, line for line."""
    manifest = folder / sync.ACTIVE_FILE
    if not manifest.is_file():
        return
    kept = [
        line
        for line in manifest.read_text(encoding="utf-8").splitlines(keepends=True)
        if not re.match(rf"^\s*-\s+{re.escape(name)}\s*$", line.rstrip("\n"))
    ]
    manifest.write_text("".join(kept), encoding="utf-8")


@dataclass
class _Edit:
    """A pending change to one file: its path and the text to put there."""

    path: Path
    text: str
    before: str | None


def _apply(edits: list[_Edit], *, category: str) -> LoadReport:
    """Write every edit, sync, and put everything back if the sync refuses.

    The restore is the whole reason this takes a list rather than one file: a
    rename moves an entry between two files, and a sync that fails halfway
    through that must not leave the question in both of them — or in neither.
    """
    for edit in edits:
        edit.path.write_text(edit.text, encoding="utf-8")
    try:
        return sync.sync_questions(category=category)
    except Exception:
        for edit in edits:
            if edit.before is None:
                edit.path.unlink(missing_ok=True)
            else:
                edit.path.write_text(edit.before, encoding="utf-8")
        raise


# --- The surface -------------------------------------------------------------


def read_entry(*, category: str, slug: str) -> AuthoredEntry:
    """The authored YAML behind one question.

    Raises rather than returning ``None`` when nothing holds the slug: a row
    with no file behind it is a question the next sync will deactivate, and the
    honest thing to tell whoever tried to edit it is that its source is missing.
    """
    folder = _category_folder(category)
    found = _find_block(folder=folder, slug=slug)
    if found is None:
        raise ValidationFailed(
            f"No resource file under {category}/ holds the question {slug!r}. "
            "It exists in the database only — the next sync will deactivate it."
        )
    path, block = found
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    entry = _parse_block("".join(lines[block.start : block.end])) or {}
    return AuthoredEntry(
        path=f"{path.parent.name}/{path.name}", category=category, entry=entry
    )


def _plan(
    *,
    target: Path,
    entry: dict[str, Any],
    existing: tuple[Path, _Block] | None,
    category: str,
    file_is_new: bool,
) -> list[_Edit]:
    """The file writes one save makes, validated and not yet on disk.

    A plain edit is one: splice the block into its file. A **rename** or a
    **retype** is two halves of a move — take the old block out, put the new one
    in — and whether those land in one file or two is the whole reason this is a
    list. Both halves composed into one text when the move is within a file
    (writing two edits to one path would have the second overwrite the first),
    two ``_Edit`` entries when it crosses one.
    """
    moved = existing is not None and (
        existing[0] != target or existing[1].slug != entry["slug"]
    )
    edits: list[_Edit] = []
    before = target.read_text(encoding="utf-8")
    working = before

    if moved:
        old_path, old_block = existing
        if old_path == target:
            working = _without_entry(working, old_block.slug)
        else:
            old_text = old_path.read_text(encoding="utf-8")
            edits.append(
                _Edit(
                    path=old_path,
                    text=_without_entry(old_text, old_block.slug),
                    before=old_text,
                )
            )

    text = _with_entry(working, entry)
    _validate(path=target, text=text, category=category)
    edits.append(_Edit(path=target, text=text, before=None if file_is_new else before))
    return edits


def save_entry(
    *, category: str, entry: dict[str, Any], original_slug: str | None = None
) -> SaveResult:
    """Write one question to its resource file, then load it.

    ``original_slug`` is what the entry was called before this edit, and is how
    a rename is told apart from a create: without it, renaming a question would
    leave the old block in place and the catalog would grow a duplicate of
    everything anybody retitled. Absent means "this is new".

    The two effects the caller gets back — the file it landed in and the
    loader's report — are both in :class:`SaveResult`, because an edit that
    wrote the file and changed no row is a thing worth seeing.
    """
    question_type = entry.get("type")
    if question_type not in QUESTION_MODELS:
        raise ValidationFailed(f"Unknown question type {question_type!r}.")
    slug = entry.get("slug")
    if not isinstance(slug, str) or not slug:
        raise ValidationFailed("A question needs a slug.")

    folder = _category_folder(category)
    existing = _find_block(folder=folder, slug=original_slug or slug)
    # Whether the file is one this call is about to invent decides how a failed
    # edit is undone: a file that existed is restored, a file that did not is
    # removed. Asked before `_ensure_file` runs, since afterwards it exists
    # either way.
    file_is_new = not _target_file(folder=folder, question_type=question_type).exists()
    if existing is None or existing[0].name != f"{question_type}.yaml":
        _reject_slug_taken_elsewhere(
            slug=slug, path=_target_file(folder=folder, question_type=question_type)
        )
    target = _ensure_file(folder=folder, question_type=question_type, category=category)

    try:
        edits = _plan(
            target=target,
            entry=entry,
            existing=existing,
            category=category,
            file_is_new=file_is_new,
        )
        action = "updated" if existing is not None else "created"
        report = _apply(edits, category=category)
    except Exception:
        # A refusal raised before `_apply` got as far as its own rollback still
        # has to undo the file `_ensure_file` may have just made, or the next
        # load fails on an empty `questions:` list nobody wrote.
        if file_is_new:
            # The manifest line goes with it. A manifest naming a file the
            # folder does not hold is a hard load failure, so leaving one
            # behind would take the whole category down over a rejected form.
            target.unlink(missing_ok=True)
            _remove_from_manifest(folder=folder, name=target.name)
        raise

    logger.info(
        "Question source written",
        action=f"authoring.{action}",
        question=slug,
        file=f"{target.parent.name}/{target.name}",
        summary=str(report),
    )
    return SaveResult(
        source=read_entry(category=category, slug=slug), action=action, report=report
    )


def set_entry_active(*, category: str, slug: str, is_active: bool) -> SaveResult:
    """Flip one question's ``is_active``, in the file and then in the row.

    A deactivation is not a delete, here for the reason it is not one in the
    loader: a matchup that already played this question points at the row. What
    changes is one line of YAML, which is what makes it reviewable — and what
    makes it survive the next sync, which would otherwise reactivate anything
    the file still lists.
    """
    source = read_entry(category=category, slug=slug)
    return save_entry(category=category, entry={**source.entry, "is_active": is_active})


def delete_entry(*, category: str, slug: str) -> LoadReport:
    """Take a question out of its file entirely.

    Not exposed by the tester, and that is deliberate — deactivation is what
    that surface offers. It exists because removing the block is the *only*
    thing that stops the loader from reviving a question, and a caller that
    genuinely wants one gone (a draft that never should have been written)
    should not have to hand-edit YAML to get it. The row still survives, stood
    down by the loader's sweep: somebody's match history points at it.
    """
    folder = _category_folder(category)
    found = _find_block(folder=folder, slug=slug)
    if found is None:
        raise ValidationFailed(f"No resource file under {category}/ holds {slug!r}.")
    path, _ = found
    before = path.read_text(encoding="utf-8")
    return _apply(
        [_Edit(path=path, text=_without_entry(before, slug), before=before)],
        category=category,
    )
