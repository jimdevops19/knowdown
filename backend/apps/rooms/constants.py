"""The numbers a room is measured against.

Separate from ``apps.matches.constants.MATCH_QUESTION_COUNTS``, which is what a
match plays when *no* room was chosen. A room states its own lengths, and these
are the bounds any of them must fall inside — a room is a set of settings, not
a way around the engine's limits.
"""

from __future__ import annotations

__all__ = [
    "MAX_ROOM_QUESTION_COUNT",
    "MIN_ROOM_QUESTION_COUNT",
]

#: The shortest match a room may run. One question is a coin toss, not a race,
#: but it is a legitimate thing to author for a demo or a themed sudden-death
#: room, so the floor is the floor and not an opinion.
MIN_ROOM_QUESTION_COUNT = 1

#: The longest. Well past ``apps.questions.constants
#: .LONGEST_MATCH_QUESTION_COUNT`` (7, what the catalog is stocked to) on
#: purpose: that number says how deep every *level band* must be, while this
#: one only stops a typo — ``questions_asked_ranges: [50]`` — from becoming a
#: room that refuses every draw with "not enough questions" long after the
#: person who wrote it has stopped looking.
MAX_ROOM_QUESTION_COUNT = 20
