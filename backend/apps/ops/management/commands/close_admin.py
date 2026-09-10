"""Shut the admin before its window expires.

    python manage.py close_admin

Closing is not required — a window expires on its own — but leaving one open
for the rest of its half hour after finishing is a habit worth not having.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ops.services import close_windows


class Command(BaseCommand):
    help = "Close every open Django admin window."

    def handle(self, *args, **options) -> None:
        closed = close_windows()
        if closed:
            self.stdout.write(self.style.SUCCESS(f"Closed {closed} admin window(s)."))
        else:
            self.stdout.write("No admin window was open.")
