"""``python -m stress.src.cli <command>`` — the four things a run consists of.

    seed        register the cast
    run         put them all in the lobby at once and report what happened
    teardown    delete every row the run created
    status      what is currently seeded, without touching the deployment

``task stress:*`` wraps each of these; see ``stress/README.md``.

Exit status is meaningful: ``run`` exits non-zero when it found problems (a
player never paired, a match that never finished, a match the server called
abandoned), so the whole cycle is something CI could be asked to pass.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Run as a script (`python stress/src/cli.py`) as well as a module: the
# relative imports below need the repo root on the path either way.
if __package__ in (None, ""):  # pragma: no cover - entry-point plumbing
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    __package__ = "stress.src"

from .config import Config  # noqa: E402
from .metrics import Metrics  # noqa: E402
from .run import print_report  # noqa: E402
from .run import run as run_load  # noqa: E402
from .seed import seed as seed_cast  # noqa: E402
from .state import STATE_FILE, RunState  # noqa: E402
from .teardown import teardown as run_teardown  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stress", description=__doc__)
    parser.add_argument("--base-url", help="Deployment under test. Overrides the config/env.")
    parser.add_argument("--config", type=Path, help="Path to an alternative config.yml.")
    parser.add_argument(
        "--verify-tls", action="store_true",
        help="Verify the server certificate (off by default: staging uses a private CA).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    seed_cmd = sub.add_parser("seed", help="Register the cast.")
    seed_cmd.add_argument(
        "--players", type=int,
        help="Accounts to register; two per matchup (default 80, i.e. 40 matchups). "
        "Also settable as KNOWDOWN_STRESS_PLAYERS.",
    )
    seed_cmd.add_argument("--room", help="Lobby room the run will queue for.")
    seed_cmd.add_argument("--seed-workers", type=int, help="Registrations in flight at once.")

    run_cmd = sub.add_parser("run", help="Put the whole cast in the lobby at once.")
    run_cmd.add_argument("--rounds", type=int, help="How many times the cast plays (default 1).")
    run_cmd.add_argument(
        "--wait-for-match", type=int,
        help="Seconds one player waits for an opponent before giving up.",
    )
    run_cmd.add_argument(
        "--join-stagger", type=float,
        help="Seconds between one player joining the queue and the next.",
    )

    down_cmd = sub.add_parser("teardown", help="Delete everything the run created.")
    down_cmd.add_argument(
        "--dry-run", action="store_true", help="Count the stress rows without deleting them."
    )
    down_cmd.add_argument(
        "--local", action="store_true",
        help="Purge a local backend in this checkout instead of exec-ing into the cluster.",
    )

    sub.add_parser("status", help="Show the currently seeded run, from the state file.")

    args = parser.parse_args(argv)

    if args.command == "status":
        return _status()

    config = Config.load(
        args.config,
        base_url=args.base_url,
        verify_tls=True if args.verify_tls else None,
        players=getattr(args, "players", None),
        room=getattr(args, "room", None),
        seed_workers=getattr(args, "seed_workers", None),
        rounds=getattr(args, "rounds", None),
        wait_for_match=getattr(args, "wait_for_match", None),
        join_stagger=getattr(args, "join_stagger", None),
    )

    if args.command == "seed":
        metrics = Metrics()
        asyncio.run(seed_cast(config=config, metrics=metrics))
        print("\n" + metrics.format_table(title="seed complete"))
        return 0

    if args.command == "run":
        state = RunState.load()
        if state.base_url != config.base_url:
            # Running against a different deployment than the one holding the
            # accounts would produce eighty 4401s and no load at all.
            raise SystemExit(
                f"State was seeded against {state.base_url}, but this run targets "
                f"{config.base_url}. Tear down and re-seed, or point at the same host."
            )
        metrics = Metrics()
        report = asyncio.run(run_load(config=config, state=state, metrics=metrics))
        return print_report(report, metrics, config=config)

    if args.command == "teardown":
        return run_teardown(config=config, dry_run=args.dry_run, local=args.local)

    return 1


def _status() -> int:
    if not STATE_FILE.exists():
        print("nothing seeded (no state file). Start with: task stress:seed")
        return 0
    state = RunState.load()
    print(f"run {state.run_id} seeded {state.created_at} against {state.base_url}")
    print(
        f"  {len(state.players)} players → {len(state.players) // 2} matchups, "
        f"room {state.room!r}"
    )
    print(f"  state file: {STATE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
