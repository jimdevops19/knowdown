"""``MEDIA_ROOT`` under the production settings module — a writable volume by
default, not the read-only code dir.

Importing ``config.settings.production`` in-process would execute it against
an already-configured Django (``config.settings.test``), so this shells out —
the only way to see what a fresh process loading that module actually gets.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_BASE_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "SECRET_KEY": "not-the-insecure-default",
    "ALLOWED_HOSTS": "example.com",
}


def _media_root(*, extra_env: dict[str, str] | None = None) -> str:
    import os

    env = {**os.environ, **_BASE_ENV, **(extra_env or {})}
    result = subprocess.run(
        [sys.executable, "-c", "from django.conf import settings; print(settings.MEDIA_ROOT)"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class ProductionMediaRootTests(SimpleTestCase):
    def test_it_defaults_to_the_data_volume(self) -> None:
        """`backend/Dockerfile` creates /data writable by the runtime user —
        the same volume a SQLite DATABASE_URL would live on — so a fresh
        deploy needs no MEDIA_ROOT configured to have somewhere durable for
        `sync_questions` to write question images."""
        self.assertEqual(_media_root(), "/data/media")

    def test_it_is_still_overridable(self) -> None:
        self.assertEqual(
            _media_root(extra_env={"MEDIA_ROOT": "/mnt/object-store/media"}),
            "/mnt/object-store/media",
        )
