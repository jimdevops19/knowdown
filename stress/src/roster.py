"""The cast: real-looking names, and the login each one gets.

Real names rather than ``user0001`` because the dashboards are not the only
thing being looked at — a lobby, a live scoreboard and a leaderboard all
render these, and "Stress Nora Whitfield vs Stress Marco Iversen" is a screen
an operator can judge at a glance.

No Faker: this project does not depend on it, and a stress test is a poor
reason to add a dependency. Two lists multiplied together give far more
distinct names than any run will ask for.

Three constraints the platform puts on the name, all enforced here so the API
never has to refuse one mid-seed (``apps.players.validators``):

* 3-30 characters of letters, digits and underscores, single spaces between
  words — so no accents, apostrophes or hyphens;
* nothing containing ``admin`` or ``knowdown``, and none of the reserved
  words;
* unique platform-wide, case-insensitively — and unique against *other runs*
  too, which is why the run id is part of every name.
"""

from __future__ import annotations

from dataclasses import dataclass

from .tags import EMAIL_DOMAIN, NAME_PREFIX, PASSWORD

#: A spread of origins, so the lobby doesn't read as one country's phone book.
#: All plain ASCII: the display-name rule has no room for anything else.
FIRST_NAMES = [
    "Nora", "Marco", "Aisha", "Tomas", "Elena", "Kwame", "Lena", "Diego",
    "Priya", "Sven", "Mira", "Hugo", "Zara", "Finn", "Ines", "Ravi",
    "Cleo", "Bruno", "Yara", "Otto", "Maya", "Luka", "Rosa", "Kai",
    "Nadia", "Pablo", "Sofia", "Emre", "Tessa", "Noah", "Ada", "Jonas",
    "Leila", "Viktor", "Anouk", "Malik", "Greta", "Andre", "Freya", "Omar",
]

LAST_NAMES = [
    "Whitfield", "Iversen", "Okafor", "Kovacs", "Delgado", "Lindqvist",
    "Bakker", "Moretti", "Novak", "Fernandes", "Haddad", "Petrov",
    "Larsen", "Castillo", "Brennan", "Yilmaz", "Dupont", "Almeida",
    "Nakamura", "Sorensen", "Vargas", "Keller", "Osei", "Ricci",
    "Jansen", "Mitchell", "Fontaine", "Zielinski", "Rahman", "Bergstrom",
]

MAX_NAME = 30


@dataclass(frozen=True)
class Persona:
    """One person: the name the platform shows, and the credentials behind it."""

    display_name: str
    email: str
    password: str


def build_roster(*, count: int, run_id: str) -> list[Persona]:
    """``count`` distinct people, all tagged for teardown.

    ``run_id`` is in both tags — the email so two runs never collide on an
    address, the display name so two runs never collide on the platform-wide
    unique name either. A run started while another is still up is a normal
    thing to do and must not fail on a constraint.
    """
    people: list[Persona] = []
    for index in range(count):
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
        people.append(
            Persona(
                display_name=_display_name(
                    first=first, last=last, run_id=run_id, index=index
                ),
                # The index, not the name, carries uniqueness in the address:
                # two people sharing a surname is a normal thing for a roster
                # to contain and an impossible thing for an email column to.
                email=f"{first.lower()}.{last.lower()}.{run_id}{index:04d}@{EMAIL_DOMAIN}",
                password=PASSWORD,
            )
        )
    return people


def _display_name(*, first: str, last: str, run_id: str, index: int) -> str:
    """``Stress Nora Whitfield a1b2 07`` — trimmed to fit.

    The prefix is the teardown's second tag (``tags.NAME_PREFIX``) and the
    suffix is what makes it unique across runs. The surname is what gets cut
    when the 30-character limit bites, because a name that has lost its
    surname still reads as a name and one that has lost its tag is one
    ``purge_stress`` can no longer find.
    """
    suffix = f"{run_id}{index:02d}"
    room_for_names = MAX_NAME - len(NAME_PREFIX) - len(suffix) - 2  # two spaces
    name = f"{first} {last}"[:room_for_names].strip()
    return f"{NAME_PREFIX} {name} {suffix}"[:MAX_NAME].strip()


def password() -> str:
    return PASSWORD
