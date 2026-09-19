"""How every row this test creates is recognised again at teardown.

These must match ``apps.matches.management.commands.purge_stress`` in the
backend — the two halves of the same contract, on opposite sides of an HTTP
boundary that no import can cross. The driver stamps; ``manage.py
purge_stress`` sweeps.

Change one, change the other.
"""

from __future__ import annotations

#: Every account the test registers gets an email here. ``.test`` is RFC
#: 2606's reserved-forever TLD, so nothing this test does can send mail to a
#: real person, whatever the target's mail configuration.
EMAIL_DOMAIN = "stress.knowdown.test"

#: Every competitor's display name starts with this word and a space. The
#: second tag, and the one that still works after an interrupted teardown has
#: already removed the account: ``Player.user`` is ``SET_NULL``, so the email
#: handle disappears the moment the login does.
NAME_PREFIX = "Stress"

#: The password every generated account uses. Staging only, and the accounts
#: it opens are deleted at teardown.
PASSWORD = "StressTest!2468"
