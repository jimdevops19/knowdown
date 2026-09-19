"""The write side of rooms: loading the lobby from its resource file.

There is no other write path. A room is a decision made in a pull request — the
same as a category or a badge — so nothing outside ``sync_rooms`` creates one.
"""

from __future__ import annotations

from apps.rooms.services.sync import ROOMS_FILE, LoadReport, sync_rooms

__all__ = ["LoadReport", "ROOMS_FILE", "sync_rooms"]
