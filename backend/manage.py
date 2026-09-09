#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys

from shared.admin_url import ADMIN_URL_ENV, generate_admin_url, normalize_admin_url


def announce_admin_url(argv):
    """For `runserver`: pick this run's admin prefix and print where it landed.

    The admin is not mounted at `/admin/` — `settings.ADMIN_URL` is a random
    40-character prefix unless one is configured. Something has to say what it
    chose or a developer with the admin enabled cannot reach it, and printing
    it here means the deployed tiers need no such affordance: nothing there
    prints a URL and nothing falls back to `admin/`.

    Seeding the environment (rather than letting settings generate its own) is
    what keeps the printed URL true: the autoreloader re-executes this file in
    a child process, which would otherwise roll a different prefix on every
    edit. `RUN_MAIN` marks that child, so this prints once per `runserver`.
    """
    if not argv[1:2] == ["runserver"]:
        return
    os.environ.setdefault(ADMIN_URL_ENV, generate_admin_url())
    if os.environ.get("RUN_MAIN") == "true":  # autoreloader child; parent printed
        return

    from django.conf import settings

    if not settings.ADMIN_ENABLED:
        print(
            f"Django admin: disabled in {os.environ['DJANGO_SETTINGS_MODULE']} "
            "(ADMIN_ENABLED).",
            flush=True,
        )
        return

    addrport = next((arg for arg in argv[2:] if not arg.startswith("-")), "127.0.0.1:8000")
    host, _, port = addrport.rpartition(":")
    host = host or "127.0.0.1"
    print(
        f"Django admin: http://{host}:{port}/{normalize_admin_url(settings.ADMIN_URL)}",
        flush=True,
    )


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    announce_admin_url(sys.argv)
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
