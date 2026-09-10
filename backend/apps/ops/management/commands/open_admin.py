"""Open the Django admin for a while, and print where it is.

    python manage.py open_admin --minutes 30 --by you@example.com

Prints one URL. That URL is the only copy of the token — it is stored hashed,
so a lost one is re-opened, never recovered. Any window already open is closed.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ops.services import DEFAULT_MINUTES, open_window, window_url


class Command(BaseCommand):
    help = "Open the Django admin at a one-time URL for a limited time."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--minutes", type=int, default=DEFAULT_MINUTES,
            help=f"How long the window stays open (default {DEFAULT_MINUTES}).",
        )
        parser.add_argument(
            "--by", default="", help="Who is opening it — recorded on the window.",
        )
        parser.add_argument(
            "--base-url", default="",
            help="Site root for the printed URL (default: https://<first ALLOWED_HOSTS entry>).",
        )

    def handle(self, *args, **options) -> None:
        if not settings.ADMIN_ENABLED:
            raise CommandError("ADMIN_ENABLED is off — there is no admin to open.")
        if not settings.ADMIN_GATE_ENABLED:
            raise CommandError(
                "ADMIN_GATE_ENABLED is off — this deployment serves the admin at "
                f"/{settings.ADMIN_URL} directly, with no window to open."
            )
        minutes = options["minutes"]
        if minutes < 1:
            raise CommandError("--minutes must be at least 1.")

        window, token = open_window(minutes=minutes, opened_by=options["by"])
        url = window_url(
            base_url=options["base_url"] or self._default_base_url(),
            token=token,
            admin_url=settings.ADMIN_URL,
        )
        self.stdout.write(self.style.SUCCESS(url))
        self.stdout.write(
            f"Open until {window.expires_at:%Y-%m-%d %H:%M:%S %Z}. "
            "Close it early with `manage.py close_admin`."
        )

    @staticmethod
    def _default_base_url() -> str:
        hosts = [h for h in settings.ALLOWED_HOSTS if h not in {"*", "localhost", "127.0.0.1"}]
        if not hosts:
            raise CommandError("Cannot guess the site URL from ALLOWED_HOSTS — pass --base-url.")
        return f"https://{hosts[0]}"
