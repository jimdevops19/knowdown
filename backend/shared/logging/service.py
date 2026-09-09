"""Which process wrote this line.

The backend image will run in more than one role — gunicorn serving the REST
API, uvicorn holding the WebSockets that carry the matchmaking pool, a
management command in an initContainer or a shell — and a log line looks
identical whichever of them emitted it. Reading them would therefore require
knowing which container the line came out of, which is fine in ``kubectl logs``
and useless the moment the lines are pooled.

So every JSON line carries ``service`` (see ``formatter.JSONFormatter``). It is
resolved once per process, at import, because a process never changes role:

- ``cli`` — ``manage.py`` (migrations, ``sync_questions``, a shell).
- ``realtime`` — the uvicorn/ASGI process: WebSockets, and its own probes.
- ``api`` — everything else, i.e. gunicorn/WSGI serving ``/api/``.

``SERVER_MODE`` is the variable the container entrypoint branches on to pick
the server, so the label cannot disagree with the process actually running. The
``manage.py`` check comes first on purpose: a command run inside the api pod
inherits that pod's ``SERVER_MODE`` and is still not the API.
"""

from __future__ import annotations

import os
import sys

API = "api"
REALTIME = "realtime"
CLI = "cli"


def _detect() -> str:
    argv0 = sys.argv[0] if sys.argv else ""
    if os.path.basename(argv0) == "manage.py":
        return CLI
    return os.environ.get("SERVER_MODE") or API


SERVICE: str = _detect()
