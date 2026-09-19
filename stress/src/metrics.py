"""What the run measures about itself.

The server's own logs and dashboards are the other half of this story — the
`action="queued"`/`"matched"`/`"answered"`/`"completed"` journey lines
``backend/CLAUDE.md`` describes are the same events seen from inside. This is
the client's side, and it is here for two reasons the server cannot cover: it
sees the *latency the caller experienced* (queueing at the ingress included,
which is the number a player would feel), and it knows which of its own calls
failed, which is how a run says "the load was applied" rather than "the load
was attempted".

Everything is keyed by a **label** — a coarse name for the call (``register``,
``answer``, ``matchmaking socket``), not the URL, because a per-UUID breakdown
is noise at this altitude.

No lock. Every writer is a coroutine on one event loop, so a ``record`` call
cannot be interrupted halfway; the threads ``rpool``'s equivalent needs one
for are not how this driver is built.
"""

from __future__ import annotations

import time
from collections import defaultdict


class Metrics:
    """Request tally for one phase of a run."""

    def __init__(self) -> None:
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._ok: dict[str, int] = defaultdict(int)
        self._failed: dict[str, int] = defaultdict(int)
        #: Answers that are a normal part of the flow rather than a fault —
        #: the 429 that means a throttle is doing its job while seeding, the
        #: 409 on a question that closed underneath a submission. Counted
        #: apart so "failed" keeps meaning "went wrong".
        self._benign: dict[str, int] = defaultdict(int)
        #: status (or exception class) -> count, for the failure breakdown a
        #: run ends with.
        self._statuses: dict[str, int] = defaultdict(int)
        self.started_at = time.monotonic()

    def record(
        self, *, label: str, seconds: float, ok: bool, status: str, benign: bool = False
    ) -> None:
        self._latencies[label].append(seconds)
        if benign:
            self._ok[label] += 1
            self._benign[label] += 1
        elif ok:
            self._ok[label] += 1
        else:
            self._failed[label] += 1
            self._statuses[status] += 1

    def snapshot(self) -> dict:
        """A copy of the tally so far, with percentiles resolved."""
        rows = []
        for label in sorted(self._latencies):
            samples = sorted(self._latencies[label])
            rows.append(
                {
                    "label": label,
                    "calls": len(samples),
                    "ok": self._ok[label],
                    "failed": self._failed[label],
                    "benign": self._benign[label],
                    "p50": _percentile(samples, 0.50),
                    "p95": _percentile(samples, 0.95),
                    "max": samples[-1] if samples else 0.0,
                }
            )
        elapsed = max(time.monotonic() - self.started_at, 1e-9)
        total = sum(r["calls"] for r in rows)
        return {
            "elapsed": elapsed,
            "total": total,
            "failed": sum(r["failed"] for r in rows),
            "benign": sum(r["benign"] for r in rows),
            "rps": total / elapsed,
            "rows": rows,
            "statuses": dict(self._statuses),
        }

    def format_table(self, *, title: str) -> str:
        snap = self.snapshot()
        head = (
            f"{title}  ·  {snap['elapsed']:6.0f}s  ·  {snap['total']:6d} calls  "
            f"·  {snap['rps']:5.1f} req/s  ·  {snap['failed']} failed"
            f"  ·  {snap['benign']} expected"
        )
        lines = [head, f"  {'call':<26}{'n':>7}{'fail':>7}{'p50':>9}{'p95':>9}{'max':>9}"]
        for row in snap["rows"]:
            lines.append(
                f"  {row['label']:<26}{row['calls']:>7}{row['failed']:>7}"
                f"{row['p50'] * 1000:>8.0f}m{row['p95'] * 1000:>8.0f}m{row['max'] * 1000:>8.0f}m"
            )
        if snap["statuses"]:
            worst = sorted(snap["statuses"].items(), key=lambda kv: -kv[1])[:6]
            lines.append("  failures: " + ", ".join(f"{k}×{v}" for k, v in worst))
        return "\n".join(lines)


def _percentile(samples: list[float], q: float) -> float:
    """Nearest-rank percentile of an already-sorted list. Good enough for a
    console readout, and free of a numpy dependency this repo doesn't have."""
    if not samples:
        return 0.0
    index = min(len(samples) - 1, max(0, round(q * len(samples) + 0.5) - 1))
    return samples[index]
