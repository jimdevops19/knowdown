"""Purge one ``load_rehearsal`` run's accounts, and only its accounts.

    uv run python manage.py load_rehearsal_teardown --run a1b2c3d4
    uv run python manage.py load_rehearsal_teardown --run a1b2c3d4 --dry-run

Filters ``accounts.User`` on the email tag ``load_rehearsal`` wrote
(``loadrehearsal-<run>-<n>@rehearsal.invalid``) and deletes exactly those
rows — real deletes, not soft: ``accounts.User`` keeps no soft delete (see
its own docstring), which is the one thing this run created that is safe to
actually remove.

**What this does not remove, and why:** each simulated account's
``players.Player`` row, and every ``Matchup`` it played, survive. Deleting a
``Player`` who has played a matchup raises on ``MatchupPlayer.player``'s own
``PROTECT`` — the same constraint that keeps anyone's match history from
being edited out from under the other side of it — and a rehearsal account
earns no exception to a rule written for exactly this reason. "Purges only
the rows the run tagged" therefore means the login identity, not the history
that identity played: a rehearsal run against shared infrastructure leaves
harmless, clearly-named (``loadrehearsal-…``) placeholder profiles and
matches behind, the same way any other completed match does. Run rehearsals
against a disposable environment if even that is unwanted.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.matches.management.commands.load_rehearsal import EMAIL_DOMAIN


class Command(BaseCommand):
    help = "Delete the accounts one load_rehearsal run created (not the matches they played)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--run", required=True, help="The --run id load_rehearsal printed.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what would be deleted; write nothing."
        )

    def handle(self, *args, **options) -> None:
        run_id = options["run"]
        if not run_id:
            raise CommandError("--run must not be empty — an empty tag would match every account.")

        prefix = f"loadrehearsal-{run_id}-"
        accounts = User.objects.filter(email__startswith=prefix, email__endswith=f"@{EMAIL_DOMAIN}")
        count = accounts.count()

        if count == 0:
            self.stdout.write(f"No accounts tagged for run {run_id!r}.")
            return

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} account(s) tagged for run {run_id!r}.")
            return

        accounts.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Deleted {count} account(s) tagged for run {run_id!r}.")
        )
        self.stdout.write(
            "Their Player rows and any matches they played were left in place — "
            "see this command's docstring for why."
        )
