"""Observe the exact accepted Domus controller; never authorize its worker."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess

PATHS = (
    ".local/bin/domus-agent-maintain",
    ".local/libexec/domus-agent-maintenance.py",
    ".local/libexec/domus-agent-runtime.py",
    ".local/libexec/domus-codex-reclaim.py",
    ".local/libexec/domus-codex-history.py",
)


def verify(home, manifest):
    if manifest.get("schema") != "limen.runtime_maintenance_observation.v1" or set(manifest.get("sha256", {})) != set(
        PATHS
    ):
        raise ValueError("observation_contract_invalid")
    if manifest.get("runtime_root") not in {"Workspace/limen/.agent-runtime", ".local/state/domus/agent-runtime"}:
        raise ValueError("observation_runtime_root_invalid")
    for name in PATHS:
        fd = os.open(home / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 1024 * 1024:
                raise ValueError("observation_source_unsafe")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                digest = hashlib.sha256(stream.read(1024 * 1024 + 1)).hexdigest()
        finally:
            os.close(fd)
        if digest != manifest["sha256"][name]:
            raise ValueError("observation_source_drift")


def observe(home: Path, manifest: dict, *, runner=run_bounded_subprocess):
    try:
        verify(home, manifest)
        environment = dict(os.environ)
        for key in (
            "DOMUS_AGENT_MAINTENANCE_IMPL",
            "DOMUS_AGENT_HOST_BIN",
            "DOMUS_AGENT_HOST_PYTHON",
            "DOMUS_AGENT_HOME",
        ):
            environment.pop(key, None)
        # launchd has no login-shell exports. Bind the reviewed migration root
        # explicitly, retaining the controller's existing containment checks.
        environment["HOME"] = str(home)
        environment["DOMUS_AGENT_RUNTIME_ROOT"] = str(home / manifest["runtime_root"])
        environment["LIMEN_AGENT_RUNTIME_ROOT"] = environment["DOMUS_AGENT_RUNTIME_ROOT"]
        result = runner(
            [str(home / PATHS[0]), "--record", "--json"],
            cwd=home,
            env=environment,
            timeout_seconds=60,
            stdout_ceiling=262144,
            stderr_ceiling=65536,
        )
        verify(home, manifest)
        payload = json.loads(result.stdout)
        if (
            result.returncode == 1
            and payload.get("schema") == "domus.runtime_maintenance.v1"
            and payload.get("status") == "blocked"
            and payload.get("reason") == "runtime maintenance is already running"
        ):
            return 1, {
                "schema": manifest["schema"],
                "status": "deferred",
                "reason": "controller_observation_busy",
                "worker_requested": False,
            }
        if (
            result.returncode not in (0, 1)
            or payload.get("schema") != "domus.runtime_maintenance.v1"
            or payload.get("recorded") is not True
        ):
            raise ValueError("observation_result_invalid")
        quota = payload["quota"]
        if quota.get("schema") != "domus.agent_runtime.v2" or quota.get("census_complete") is not True:
            raise ValueError("observation_census_incomplete")
        if payload.get("worker", {}).get("recovery_status") != "not_requested":
            raise ValueError("observation_worker_unexpected")
        report = {
            "schema": manifest["schema"],
            "source_revision": manifest["source_revision"],
            "status": payload["status"],
            "observed_at": payload["observed_at"],
            "consumption_bytes": quota["total_size_bytes"],
            "pool": quota["pool"],
            "worker_requested": False,
            "bookkeeping_only": True,
        }
        return result.returncode, report
    except (OSError, ValueError, KeyError, TypeError, BoundedSubprocessError) as exc:
        return 78, {
            "schema": "limen.runtime_maintenance_observation.v1",
            "status": "failed",
            "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
        }
