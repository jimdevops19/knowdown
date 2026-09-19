"""Delete everything a ``stress/`` run created, found by its tags.

    python manage.py purge_stress --dry-run
    python manage.py purge_stress --yes

This is phase three of the load test that lives in ``stress/`` at the repo
root — see ``stress/README.md``. It runs **inside** the deployment
(``kubectl exec`` from ``stress/src/teardown.py``), because deleting an
account is not something the API offers and should not be.

**It finds rows by their tags, never by a state file.** The driver stamps two
of them and this command sweeps both, so a run whose ``.state/run.json`` was
lost — or two runs overlapping — still leaves a cleanable database:

===================  =====================================================
account              email at ``@stress.knowdown.test`` (RFC 2606's
                     reserved-forever TLD, so nothing here can misfire at a
                     real inbox)
competitor           ``Player.display_name`` starts with ``Stress`` — the
                     second handle, and the one that still works after
                     ``Player.user`` has been ``SET_NULL``'d by an earlier,
                     partial teardown
===================  =====================================================

The driver's copy of the tags lives in ``stress/src/tags.py``. They are two
halves of one contract across an HTTP boundary no import can cross — change
one, change the other.

**Hard deletes, not the platform's usual soft delete.** A soft-deleted
``Player`` still holds its display name in the unique index and still shows
up in ``all_objects``; a stress run that left a thousand of those behind
would be a slow leak dressed up as a teardown. ``Matchup``,
``MatchupPlayer``, ``MatchupQuestion``, ``PlayerAnswer``, ``Ranking`` and
``PlayerAchievement`` all go for real, in that order — leaf-first, because
``MatchupPlayer.player`` and ``PlayerAnswer.player`` are ``PROTECT`` and a
``Player`` cannot be removed while a match it played still points at it.

**A matchup with a real person on the other side is left alone**, and so is
the stress ``Player`` inside it. That pairing is not supposed to happen
(a stress run is meant to have staging to itself) but it *can*: the pool is
global, and anybody tapping "play" during a run joins the same queue. Half of
a match is not a thing to delete — it would edit a real person's history, the
same objection ``MatchupPlayer.player``'s ``PROTECT`` exists to raise — so
the match stays, the stress competitor stays holding its side of it, and only
the login goes. What is left is inert and clearly named, and the command says
how much of it there is rather than reporting a clean sweep it did not make.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from apps.accounts.models import User
from apps.achievements.models import PlayerAchievement
from apps.matches.models import Matchup, MatchupPlayer, MatchupQuestion, PlayerAnswer
from apps.players.models import Player
from apps.rankings.models import Ranking
from shared.logging import get_logger

logger = get_logger(__name__)

#: Must match ``stress/src/tags.py``. See this module's docstring.
EMAIL_DOMAIN = "stress.knowdown.test"
NAME_PREFIX = "Stress"


def stress_players():
    """Every competitor a stress run stood up, by either tag.

    ``all_objects``: a soft-deleted row is still a row, still holds its name
    in the unique index, and is exactly what an interrupted teardown leaves
    behind — so the sweep has to see it.
    """
    return Player.all_objects.filter(
        Q(user__email__iendswith=f"@{EMAIL_DOMAIN}")
        | Q(display_name__startswith=f"{NAME_PREFIX} ")
    ).distinct()


def _split_matchups(player_ids):
    """The matchups to delete, and the ones to leave alone.

    A matchup is deletable only when **every** one of its sides is a stress
    competitor. One with a real person on the other side is somebody's match
    history, and this command does not edit that — see the module docstring.
    """
    touched = Matchup.all_objects.filter(players__player_id__in=player_ids).distinct()
    annotated = touched.annotate(
        side_count=Count("players", distinct=True),
        stress_side_count=Count(
            "players", filter=Q(players__player_id__in=player_ids), distinct=True
        ),
    )
    ours = [m.id for m in annotated if m.side_count == m.stress_side_count]
    shared = [m.id for m in annotated if m.side_count != m.stress_side_count]
    return ours, shared


class Command(BaseCommand):
    help = "Hard-delete every row a stress/ run created, found by its tags."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count the tagged rows and write nothing.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required to actually delete. Deleting is not the default "
            "for the same reason `migrate` does not run itself.",
        )

    def handle(self, *args, **options) -> None:
        dry_run = options["dry_run"]
        if not dry_run and not options["yes"]:
            self.stdout.write(
                self.style.ERROR(
                    "Refusing to delete without --yes. Use --dry-run to see the count first."
                )
            )
            return

        players = stress_players()
        player_ids = list(players.values_list("id", flat=True))
        accounts = User.objects.filter(email__iendswith=f"@{EMAIL_DOMAIN}")
        ours, shared = _split_matchups(player_ids)

        counts = {
            "accounts": accounts.count(),
            "players": len(player_ids),
            "matchups": len(ours),
            "questions": MatchupQuestion.objects.filter(matchup_id__in=ours).count(),
            "answers": PlayerAnswer.objects.filter(player_id__in=player_ids).count(),
            "rankings": Ranking.all_objects.filter(player_id__in=player_ids).count(),
            "badges": PlayerAchievement.objects.filter(player_id__in=player_ids).count(),
        }
        self._report("tagged", counts, shared=len(shared))

        if dry_run:
            self.stdout.write("Dry run — nothing was deleted.")
            return
        if not player_ids and not counts["accounts"]:
            self.stdout.write("Nothing tagged. The deployment is already clean.")
            return

        with transaction.atomic():
            # Leaf-first. Every one of these is a real delete: `Ranking` and
            # `Matchup` are BaseModel subclasses, whose `.delete()` would
            # only stamp `deleted_at`.
            PlayerAnswer.objects.filter(player_id__in=player_ids).delete()
            PlayerAnswer.objects.filter(matchup_question__matchup_id__in=ours).delete()
            MatchupQuestion.objects.filter(matchup_id__in=ours).delete()
            MatchupPlayer.all_objects.filter(matchup_id__in=ours).hard_delete()
            Matchup.all_objects.filter(id__in=ours).hard_delete()
            Ranking.all_objects.filter(player_id__in=player_ids).hard_delete()
            PlayerAchievement.objects.filter(player_id__in=player_ids).delete()
            # Whatever is still referenced by a shared matchup stays; the
            # rest goes. Asking the database which is which beats predicting
            # it — a PROTECT that fires here would roll back the whole sweep.
            protected = set(
                MatchupPlayer.all_objects.filter(player_id__in=player_ids).values_list(
                    "player_id", flat=True
                )
            ) | set(
                PlayerAnswer.objects.filter(player_id__in=player_ids).values_list(
                    "player_id", flat=True
                )
            )
            removable = [pid for pid in player_ids if pid not in protected]
            Player.all_objects.filter(id__in=removable).hard_delete()
            # Last: `Player.user` is SET_NULL, so an account removed earlier
            # would have quietly orphaned a competitor still to be found.
            deleted_accounts = accounts.count()
            accounts.delete()

        left = {
            "accounts": User.objects.filter(email__iendswith=f"@{EMAIL_DOMAIN}").count(),
            "players": stress_players().count(),
            "matchups": len(shared),
        }
        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {len(removable)} competitor(s) and {deleted_accounts} account(s)."
            )
        )
        self._report("left behind", left, shared=len(shared))
        if any(left.values()):
            self.stdout.write(
                "What is left is held by a matchup a real player was in — see this "
                "command's docstring. It is inert, and named `Stress …` so it can "
                "be recognised."
            )
        logger.info(
            "Stress data purged",
            count=len(removable),
            summary=", ".join(f"{k}={v}" for k, v in counts.items()),
        )

    def _report(self, title: str, counts: dict, *, shared: int) -> None:
        self.stdout.write(f"{title}:")
        for label, value in counts.items():
            self.stdout.write(f"  {label:<12}{value:>8}")
        if shared:
            self.stdout.write(
                f"  {'shared':<12}{shared:>8}  (matchups with a real player on the other side)"
            )
