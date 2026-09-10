"""The shape of ``resources/achievements.yaml``.

One entry, one shape — unlike ``apps.questions``, a badge has no variants to
discriminate on, so this is the whole schema. Strict for the same reason the
question specs are: a misspelled key should be a load error, not a silent
default.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AchievementSpec(BaseModel):
    """One entry in ``resources/achievements.yaml``."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=100)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    is_active: bool = True
