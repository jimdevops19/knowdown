"""Phase one: build the cast, through the public API.

Everything here is an ordinary HTTP call a real client could make — no ORM,
no fixtures, no shortcut through the admin. That is the point: the rows this
leaves behind are exactly the rows the app itself produces, ``Player``,
auto-name and all, and the seeding traffic is itself the first thing the
target's logs show.

What it builds: ``cast.players`` accounts, each claiming a tagged display
name afterwards the way the SPA's welcome screen does
(``PATCH /players/me/``). Nothing else — a stress run has no tournaments to
stand up, and a lobby is loaded from ``rooms.yaml`` by the deployment, not by
a client.

**Signing up is the slow part, and that is the platform working.**
``RegisterView`` is on the ``login`` throttle scope — 10/min per IP by
default — and every one of these comes from one machine. The client waits out
a 429 rather than failing it (``client.Api.request``), so the default 80
accounts take roughly eight minutes against an unmodified target. See
``stress/README.md`` for the ``THROTTLE_LOGIN`` override that makes this a
few seconds instead, and why the seed is a separate command from the run.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone

from .client import Api, ApiError
from .config import Config
from .metrics import Metrics
from .roster import Persona, build_roster
from .state import RunState, SeededPlayer


async def seed(*, config: Config, metrics: Metrics) -> RunState:
    run_id = secrets.token_hex(2)
    print(
        f"seeding run {run_id} against {config.base_url}: "
        f"{config.players} players for {config.matchups} simultaneous matchups"
    )
    await _check_room(config=config, metrics=metrics)

    personas = build_roster(count=config.players, run_id=run_id)
    players = await _register_all(personas=personas, config=config, metrics=metrics)
    print(f"  registered {len(players)}/{len(personas)} accounts")

    if len(players) < 2:
        raise SystemExit(
            "Fewer than two accounts came up — there is nobody to pair. "
            "Check the errors above."
        )
    if len(players) % 2:
        # Better to seed an odd number and report it than to have the run
        # leave one player in a queue nobody joins and call that a finding.
        print("  note: an odd number of accounts came up; one will sit out each round")

    state = RunState(
        run_id=run_id,
        base_url=config.base_url,
        room=config.room,
        created_at=datetime.now(timezone.utc).isoformat(),
        players=players,
    )
    path = state.save()
    print(f"  state written to {path}")
    return state


async def _check_room(*, config: Config, metrics: Metrics) -> None:
    """Fail now, with a list, rather than eighty sockets from now with a 4404.

    An unknown room closes the matchmaking socket with ``CLOSE_NOT_FOUND``
    and nothing else — by design, since a socket for something that is not
    there should not explain itself — so a typo in ``--room`` would otherwise
    surface as every player failing to be matched, which looks exactly like a
    broken pool.
    """
    api = Api(
        base_url=config.base_url,
        metrics=metrics,
        verify=config.verify_tls,
        timeout=config.timeout,
        max_retries=config.seed_max_retries,
    )
    try:
        rooms = await api.get("/api/v1/rooms/", label="list rooms", auth=False)
    except ApiError as exc:
        # The lobby is `IsAuthenticated` on some tiers; a refusal here is not
        # a reason to refuse to seed, it just costs the check.
        print(f"  note: could not read the lobby to check the room ({exc}); continuing")
        return
    finally:
        await api.aclose()

    slugs = [room["slug"] for room in rooms] if isinstance(rooms, list) else []
    if slugs and config.room not in slugs:
        raise SystemExit(
            f"No room {config.room!r} in the lobby. Available: {', '.join(slugs)}"
        )
    for room in rooms if isinstance(rooms, list) else []:
        if room.get("slug") == config.room and room.get("question_pool_size", 1) == 0:
            raise SystemExit(
                f"Room {config.room!r} can draw no questions — its filters have "
                "outrun the catalog. `manage.py questions_report` on the target."
            )


async def _register_all(
    *, personas: list[Persona], config: Config, metrics: Metrics
) -> list[SeededPlayer]:
    """Register everybody and keep the ones that came up.

    A failure here is reported and dropped rather than fatal: eighty signups
    against a deployment about to be deliberately overloaded is exactly the
    moment a couple of them might not make it, and a run of 78 is still worth
    having.

    ``seed.workers`` in flight at a time, not all of them: the throttle
    refuses everything past the tenth in a minute anyway, so more concurrency
    buys nothing but a longer queue of clients sleeping on ``Retry-After``.
    """
    semaphore = asyncio.Semaphore(config.seed_workers)
    done = 0
    players: list[SeededPlayer] = []
    failures: list[str] = []

    async def register(persona: Persona) -> None:
        nonlocal done
        async with semaphore:
            api = Api(
                base_url=config.base_url,
                metrics=metrics,
                verify=config.verify_tls,
                timeout=config.timeout,
                max_retries=config.seed_max_retries,
            )
            try:
                await api.register(email=persona.email, password=persona.password)
                # The second half of signing up: registration takes no name,
                # so this is where the persona is actually named — and where
                # it gets the display-name tag `purge_stress` can still find
                # after `Player.user` has been SET_NULL'd.
                player = await api.patch(
                    "/api/v1/players/me/",
                    json={"display_name": persona.display_name},
                    label="claim name",
                )
                players.append(
                    SeededPlayer(
                        email=persona.email,
                        password=persona.password,
                        display_name=persona.display_name,
                        player_id=str(player["id"]),
                        access=api.access or "",
                        refresh=api.refresh_cookie or "",
                    )
                )
            except ApiError as exc:
                failures.append(f"{persona.email}: {exc}")
            finally:
                await api.aclose()
                done += 1
                if done % 10 == 0:
                    print(f"    {done}/{len(personas)} accounts")

    await asyncio.gather(*(register(persona) for persona in personas))

    for line in failures[:10]:
        print(f"    ! {line}")
    if len(failures) > 10:
        print(f"    ! … and {len(failures) - 10} more registration failures")
    return players
