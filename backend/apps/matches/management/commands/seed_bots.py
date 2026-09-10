"""Author the 50-bot roster ``apps.matches.bots`` pairs a lonely player with.

    uv run python manage.py seed_bots
    uv run python manage.py seed_bots --count 50   # the default; any size works
    uv run python manage.py seed_bots --dry-run

**Idempotent, upserting on display name** — the same posture
``sync_questions`` takes on ``slug`` (``backend/CLAUDE.md``): re-running this
after tuning the accuracy/speed curve below corrects the existing 50 rows
rather than inserting 50 more beside them. A bot is never deleted by this
command, only ever created or updated — one may already be the recorded
opponent in a played matchup (``MatchupPlayer.player`` is ``PROTECT``,
same as a human's), so removing the row is not this command's decision to
make any more than deactivating a question is `sync_questions`'s to reverse
by deleting one.

The roster is **leveled, not uniform**: bot 1 of *n* is the weakest — ~30%
accurate, and slow (answers with a **fraction of the clock**, not a fixed
number of seconds, already gone) — and bot *n* is the strongest — ~90%
accurate and fast (answers with only a small fraction of the clock spent) —
with every bot in between interpolated linearly on both axes together. That
is a deliberate choice, not the only valid one: a slow-but-accurate or
fast-but-careless bot is a fine opponent too, and nothing about
``BotProfile`` requires the two numbers to move together. Interpolating them
together is simply the simplest curve that spans both requested ranges
end-to-end with a plausible "skill level" story a player can learn to read.

Speed is authored as a **percentage of the question's own time limit**, not a
fixed millisecond band — see ``BotProfile.min_response_fraction``'s docstring
for why a fixed band cannot mean the same thing on a matrix question's 20s
clock as it does on the 10s fallback.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.matches.models import BotProfile
from apps.players.models import Player

#: The full span the roster interpolates across. Matches the brief: the
#: weakest bot's guessing probability is 30%, the strongest's is 90%; the
#: weakest bot answers with a mean of ~90% of a question's clock already
#: spent, the strongest with a mean of ~20% spent — whatever that question's
#: own time limit turns out to be.
_MIN_ACCURACY = 0.30
_MAX_ACCURACY = 0.90
_SLOWEST_MEAN_FRACTION = 0.90
_FASTEST_MEAN_FRACTION = 0.20
#: Width of one bot's own response band, as a fraction of the clock. Narrow
#: enough that a bot is recognisably fast or slow rather than merely random,
#: wide enough that the same bot does not answer at the exact same instant
#: every question.
_RESPONSE_BAND_WIDTH_FRACTION = 0.12
_MIN_RESPONSE_FRACTION_FLOOR = 0.05


class Command(BaseCommand):
    help = "Create or update the CPU opponent roster apps.matches.bots draws from."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count", type=int, default=50, help="Roster size. Default: 50."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        if count < 1:
            self.stderr.write(self.style.ERROR("--count must be at least 1."))
            return

        created = updated = 0
        for level in range(1, count + 1):
            display_name, accuracy, min_fraction, max_fraction = _bot_spec(level=level, count=count)
            if options["dry_run"]:
                self.stdout.write(
                    f"{display_name}: accuracy={accuracy:.0%} "
                    f"response={min_fraction:.0%}-{max_fraction:.0%} of the clock"
                )
                continue
            was_created = _upsert_bot(
                display_name=display_name,
                accuracy=accuracy,
                min_fraction=min_fraction,
                max_fraction=max_fraction,
            )
            created += was_created
            updated += not was_created

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"{count} bot(s) would be written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Bots synced: {created} created, {updated} updated.")
            )


def _bot_spec(*, level: int, count: int) -> tuple[str, float, float, float]:
    """The name and ``BotProfile`` numbers for roster slot ``level`` (1-indexed,
    1 = weakest). Pure and deterministic, so re-running the command with the
    same ``count`` always describes the same 50 bots."""
    fraction = (level - 1) / (count - 1) if count > 1 else 1.0
    accuracy = _MIN_ACCURACY + fraction * (_MAX_ACCURACY - _MIN_ACCURACY)
    mean_fraction = _SLOWEST_MEAN_FRACTION + fraction * (
        _FASTEST_MEAN_FRACTION - _SLOWEST_MEAN_FRACTION
    )
    min_fraction = max(
        _MIN_RESPONSE_FRACTION_FLOOR, mean_fraction - _RESPONSE_BAND_WIDTH_FRACTION / 2
    )
    max_fraction = min(1.0, mean_fraction + _RESPONSE_BAND_WIDTH_FRACTION / 2)
    return f"CPU-{level:02d}", round(accuracy, 4), round(min_fraction, 4), round(max_fraction, 4)


@transaction.atomic
def _upsert_bot(*, display_name: str, accuracy: float, min_fraction: float, max_fraction: float) -> bool:
    """Returns ``True`` if a new bot ``Player``/``BotProfile`` pair was
    created, ``False`` if an existing one was updated in place."""
    # Not `get_or_create(display_name__iexact=...)`: Django cannot build a
    # `create()` call back out of a lookup kwarg, so this is the explicit
    # get-then-create the case-insensitive constraint (`Player.Meta`) asks for
    # anyway.
    player = Player.objects.filter(display_name__iexact=display_name).first()
    created = player is None
    if created:
        player = Player.objects.create(
            display_name=display_name, is_bot=True, has_auto_name=False
        )
    elif not player.is_bot:
        # A human happens to hold this exact name — extremely unlikely given
        # the CPU-NN shape, but a collision must never silently promote a
        # person's row into a bot's.
        raise ValueError(f"Display name {display_name!r} already belongs to a human player.")

    BotProfile.objects.update_or_create(
        player=player,
        defaults={
            "accuracy": accuracy,
            "min_response_fraction": min_fraction,
            "max_response_fraction": max_fraction,
        },
    )
    return created
