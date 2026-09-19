"""Run configuration: the YAML file, plus the environment and flags on top.

The file is the default shape of a run (how many players, how many rounds,
how fast they answer); the environment is where the *deployment* comes from,
because the staging hostname carries the Mac's LAN IP and changes with the
DHCP lease — pinning it in a committed file would make the file wrong roughly
once a week.

``KNOWDOWN_STRESS_PLAYERS`` is in the environment for a different reason: it
is the one number an operator reaches for between runs ("the same test, but
crowded"), and an environment variable is what survives being passed through
``task`` without every task growing a flag.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yml"

#: A matchup is a race between exactly two people
#: (``apps.matches.constants.PLAYERS_PER_MATCHUP``). Stated here so the
#: driver's "players -> matchups" arithmetic has a name rather than a 2 in it.
PLAYERS_PER_MATCHUP = 2


@dataclass
class Config:
    # --- deployment under test ---
    base_url: str
    verify_tls: bool
    timeout: float
    #: kubectl coordinates for the teardown, which has to run *inside* the
    #: cluster (deleting an account is not something the API offers).
    kube_context: str
    kube_namespace: str
    kube_deployment: str

    # --- the cast ---
    players: int
    room: str

    # --- the load ---
    rounds: int
    answer_delay: tuple[float, float]
    wait_for_match_seconds: int
    join_stagger_seconds: float

    # --- seeding ---
    seed_workers: int
    seed_max_retries: int

    raw: dict = field(default_factory=dict)

    @property
    def matchups(self) -> int:
        """How many games run at once — the number this test is really about."""
        return self.players // PLAYERS_PER_MATCHUP

    @classmethod
    def load(cls, path: Path | None = None, **overrides) -> "Config":
        data = yaml.safe_load((path or DEFAULT_CONFIG).read_text()) or {}
        target = data.get("target", {})
        cast = data.get("cast", {})
        load = data.get("load", {})
        seed = data.get("seed", {})
        delay = load.get("answer_delay_seconds", [1.0, 4.0])

        config = cls(
            base_url=(
                overrides.get("base_url")
                or os.environ.get("KNOWDOWN_STRESS_BASE_URL")
                or target.get("base_url", "")
            ).rstrip("/"),
            verify_tls=_first(overrides.get("verify_tls"), target.get("verify_tls", False)),
            timeout=float(target.get("timeout_seconds", 30)),
            kube_context=(
                os.environ.get("KNOWDOWN_STRESS_CONTEXT") or target.get("kube_context", "")
            ),
            kube_namespace=(
                os.environ.get("KNOWDOWN_STRESS_NAMESPACE") or target.get("kube_namespace", "")
            ),
            kube_deployment=target.get("kube_deployment", "backend"),
            players=int(
                _first(
                    overrides.get("players"),
                    os.environ.get("KNOWDOWN_STRESS_PLAYERS"),
                    cast.get("players", 80),
                )
            ),
            room=(
                overrides.get("room")
                or os.environ.get("KNOWDOWN_STRESS_ROOM")
                or cast.get("room", "nba-room-general")
            ),
            rounds=int(
                _first(
                    overrides.get("rounds"),
                    os.environ.get("KNOWDOWN_STRESS_ROUNDS"),
                    load.get("rounds", 1),
                )
            ),
            answer_delay=(float(delay[0]), float(delay[-1])),
            wait_for_match_seconds=int(
                _first(
                    overrides.get("wait_for_match"), load.get("wait_for_match_seconds", 120)
                )
            ),
            join_stagger_seconds=float(
                _first(
                    overrides.get("join_stagger"), load.get("join_stagger_seconds", 0.05)
                )
            ),
            seed_workers=int(_first(overrides.get("seed_workers"), seed.get("workers", 4))),
            seed_max_retries=int(seed.get("max_retries", 12)),
            raw=data,
        )

        if not config.base_url:
            raise SystemExit(
                "No base URL. Set KNOWDOWN_STRESS_BASE_URL (e.g. "
                "https://knowdown.10.100.102.7.nip.io), pass --base-url, or fill in "
                f"target.base_url in {DEFAULT_CONFIG}."
            )
        _refuse_production(config.base_url)
        config.sanity()
        return config

    def sanity(self) -> None:
        """Refuse numbers that cannot produce a run, before anything is
        registered — the alternative is discovering it 60 signups in."""
        if self.players < PLAYERS_PER_MATCHUP:
            raise SystemExit(
                f"{self.players} players cannot play anybody. A matchup needs "
                f"{PLAYERS_PER_MATCHUP}."
            )
        if self.players % PLAYERS_PER_MATCHUP:
            # Rounded down rather than refused: "150" is a perfectly clear
            # thing for an operator to ask for, and the alternative is one
            # player left in a queue no second player will ever join, which
            # reads in the results as a platform failure it isn't.
            self.players -= self.players % PLAYERS_PER_MATCHUP
            print(
                f"  note: players rounded down to {self.players} — a matchup is a race "
                f"between exactly {PLAYERS_PER_MATCHUP}."
            )
        if self.rounds < 1:
            raise SystemExit("--rounds must be at least 1.")


def _first(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _refuse_production(base_url: str) -> None:
    """This test registers hundreds of accounts and plays thousands of
    questions. Staging and local are the places for that. There is no
    production tier yet; when there is, this is the guard that has to know
    about it, so it fails closed on anything that isn't recognisably not-prod.
    """
    allowed_markers = ("nip.io", "localhost", "127.0.0.1", "staging", ".test", ".local")
    if not any(marker in base_url for marker in allowed_markers):
        raise SystemExit(
            f"{base_url} does not look like a staging or local deployment. "
            "The stress test refuses to run anywhere else; set "
            "KNOWDOWN_STRESS_BASE_URL to a staging host."
        )
