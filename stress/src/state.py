"""The run's ledger: who was registered, so the load phase can drive them and
``stress status`` can say what is currently seeded.

Seeding and running are separate commands on purpose. Registering 80 accounts
against a throttled signup door is slow (see ``stress/README.md``), and doing
it again every time you want another round of load would be both wasteful and
a different test. So the seed writes this file and the run reads it.

It holds passwords and JWTs for throwaway staging accounts, which is why
``.state/`` is git-ignored. It is *not* the source of truth for teardown —
``manage.py purge_stress`` finds rows by their tags, so a lost state file
still leaves a cleanable database.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / ".state"
STATE_FILE = STATE_DIR / "run.json"


@dataclass
class SeededPlayer:
    email: str
    password: str
    display_name: str
    player_id: str
    access: str = ""
    #: The refresh token, lifted out of the HttpOnly cookie the API set. Kept
    #: because it is the cheap door back in: rotating it is on the ordinary
    #: `anon` ceiling, while signing 80 accounts in is on `login`'s much
    #: tighter one.
    refresh: str = ""


@dataclass
class RunState:
    run_id: str
    base_url: str
    room: str
    created_at: str
    players: list[SeededPlayer] = field(default_factory=list)

    def save(self, path: Path = STATE_FILE) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, path: Path = STATE_FILE) -> "RunState":
        if not path.exists():
            raise SystemExit(
                f"No run state at {path}. Seed first: `task stress:seed` "
                "(or `python -m stress.src.cli seed`)."
            )
        data = json.loads(path.read_text())
        return cls(
            run_id=data["run_id"],
            base_url=data["base_url"],
            room=data["room"],
            created_at=data["created_at"],
            players=[SeededPlayer(**p) for p in data["players"]],
        )
