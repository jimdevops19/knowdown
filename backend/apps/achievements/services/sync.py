"""Loading ``resources/achievements.yaml`` into the ``Achievement`` table.

The same authoring loop as ``apps.questions.services.sync``, at a tenth of the
size because a badge has one shape and no images to resolve:

- **Upserted on ``slug``**, so correcting a badge's wording re-runs into the
  same row instead of a second one.
- **Nothing is deleted.** A badge dropped from the file is deactivated —
  ``PlayerAchievement`` rows already awarded still point at it.
- **Every entry is validated before anything is written.**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from django.db import transaction

from apps.achievements.models import Achievement
from apps.achievements.schemas import AchievementSpec
from apps.core_common.exceptions import ValidationFailed
from shared.logging import get_logger

logger = get_logger(__name__)

#: apps/achievements/services/sync.py -> apps/achievements/resources
RESOURCES = Path(__file__).resolve().parent.parent / "resources"
ACHIEVEMENTS_FILE = RESOURCES / "achievements.yaml"


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


def _read_specs(*, path: Path) -> list[AchievementSpec]:
    if not path.exists():
        raise ValidationFailed(f"Resource file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValidationFailed(f"{path.name} must be a list of achievements.")

    specs, problems = [], []
    for index, entry in enumerate(raw):
        try:
            specs.append(AchievementSpec.model_validate(entry))
        except Exception as exc:
            slug = entry.get("slug", "?") if isinstance(entry, dict) else "?"
            problems.append(f"{path.name}[{index}] ({slug}): {exc}")
    if problems:
        raise ValidationFailed("Invalid achievements.", details=problems)

    seen: dict[str, int] = {}
    for spec in specs:
        seen[spec.slug] = seen.get(spec.slug, 0) + 1
    duplicates = sorted(slug for slug, count in seen.items() if count > 1)
    if duplicates:
        raise ValidationFailed(f"Duplicate achievement slugs: {', '.join(duplicates)}")

    return specs


@transaction.atomic
def sync_achievements(*, path: Path | None = None) -> LoadReport:
    """Upsert the catalog from ``resources/achievements.yaml``."""
    source = path or ACHIEVEMENTS_FILE
    specs = _read_specs(path=source)

    report = LoadReport()
    for spec in specs:
        _, created = Achievement.all_objects.update_or_create(
            slug=spec.slug,
            defaults={
                "name": spec.name,
                "description": spec.description,
                "is_active": spec.is_active,
                # Revive rather than insert beside it — see
                # apps.questions.services.sync.sync_categories.
                "deleted_at": None,
            },
        )
        (report.created if created else report.updated).append(spec.slug)

    seen = {spec.slug for spec in specs}
    stale = Achievement.objects.filter(is_active=True).exclude(slug__in=seen)
    report.deactivated = sorted(stale.values_list("slug", flat=True))
    stale.update(is_active=False)

    logger.info("Achievements synced", summary=str(report), file=source.name)
    return report
