"""Phase three: put the deployment back the way it was found.

The teardown cannot be an API call — deleting an account is not something the
API offers, and should not be. So it runs ``manage.py purge_stress``
*inside* the deployment: over ``kubectl exec`` against staging, or directly
when the target is a backend in this checkout.

It finds rows by their tags, not by the run-state file (see
:mod:`stress.src.tags`), which is what makes it able to clean up after a run
whose state file was lost, or after two runs at once — and what makes it the
thing to reach for when a run was interrupted halfway.

**``purge_stress`` has to exist in the deployed image.** After pulling a
change to it, ``task publish:local:backend && task rollout:staging:backend``
before relying on this.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Config
from .state import STATE_FILE

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"


def teardown(*, config: Config, dry_run: bool = False, local: bool = False) -> int:
    """Run the purge and report it. Returns the command's exit status."""
    args = ["purge_stress"] + (["--dry-run"] if dry_run else ["--yes"])

    status = _run_local(args) if local else _run_in_cluster(config=config, args=args)

    if status == 0 and not dry_run and STATE_FILE.exists():
        # The state file now describes accounts that no longer exist; leaving
        # it would let `stress run` be pointed at deleted players and spend a
        # whole round collecting 401s.
        STATE_FILE.unlink()
        print(f"removed {STATE_FILE}")
    return status


def _run_local(args: list[str]) -> int:
    """Against a local server: the same command, run in this checkout."""
    command = ["uv", "run", "python", "manage.py", *args]
    print(f"$ {' '.join(command)}  (in {BACKEND_DIR})")
    return subprocess.run(command, cwd=BACKEND_DIR, check=False).returncode


def _run_in_cluster(*, config: Config, args: list[str]) -> int:
    """Against staging: exec into a running backend pod.

    ``kubectl exec deployment/<name>`` picks one of its pods, which is the
    right semantics here — every replica shares one database, so any of them
    can do the deleting. The ``backend`` deployment rather than ``realtime``
    for no better reason than that it is the one that owns the schema; either
    runs the same image.
    """
    if shutil.which("kubectl") is None:
        raise SystemExit(
            "kubectl not found. Either install it, or run the purge yourself "
            "inside the cluster:\n"
            f"  kubectl -n {config.kube_namespace} exec deployment/"
            f"{config.kube_deployment} -- python manage.py purge_stress --yes"
        )
    if not config.kube_namespace:
        raise SystemExit(
            "No Kubernetes namespace configured. Set target.kube_namespace in "
            "stress/config.yml (or KNOWDOWN_STRESS_NAMESPACE), or pass --local."
        )

    command = ["kubectl"]
    if config.kube_context:
        command += ["--context", config.kube_context]
    command += [
        "-n", config.kube_namespace,
        "exec", f"deployment/{config.kube_deployment}",
        "--", "python", "manage.py", *args,
    ]
    print(f"$ {' '.join(command)}")
    return subprocess.run(command, check=False).returncode
