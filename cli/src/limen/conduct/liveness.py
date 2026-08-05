"""Foreign-occupant probe for worktree succession.

Registration may name a dead predecessor to supersede (ConductorSessionV1.supersedes), but the
broker cannot verify process liveness across hosts — the claimant must, and it runs INSIDE the
worktree it is claiming, so the plain is-anything-alive-here probe would always answer "yes, me."
This probe therefore excludes the calling process's own ancestor lineage (the boot shell, the
workstream launcher, the tmux pane) and reports only FOREIGN occupants.

Sibling of scripts/_worktree_liveness.py, which serves repo scripts that run without the limen
package installed and needs no self-exclusion (the stream launcher probes before it spawns into
the worktree). Both fail CLOSED: when the probe itself is unavailable, the answer is "occupied"
(pid -1), so a broken probe can only refuse succession, never steal a live session's worktree.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _ancestor_pids() -> set[int]:
    """The calling process and its ancestor chain, walked via `ps` (portable to macOS)."""
    lineage = {os.getpid()}
    pid = os.getpid()
    for _ in range(64):
        try:
            raw = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                cwd="/",
            ).stdout.strip()
            parent = int(raw)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            break
        if parent <= 1 or parent in lineage:
            break
        lineage.add(parent)
        pid = parent
    return lineage


def _process_cwds() -> dict[Path, int]:
    """Observable process cwds; an unavailable probe fails closed (pid -1 owns everything)."""
    observed: dict[Path, int] = {}
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                observed[(entry / "cwd").resolve(strict=True)] = int(entry.name)
            except (OSError, ValueError):
                continue
        return observed
    try:
        # cwd="/" is load-bearing: the scanner subprocess otherwise inherits the CALLER's cwd,
        # and the claimant registers from inside the worktree it probes — so lsof would list
        # ITSELF as a live occupant of that worktree, a descendant the ancestor lineage cannot
        # exclude, and succession would be refused deterministically (the 2026-07-30 reopen
        # incident). Launching the observer from / keeps it out of every observed region.
        result = subprocess.run(
            ["lsof", "-n", "-a", "-d", "cwd", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            cwd="/",
        )
    except (OSError, subprocess.TimeoutExpired):
        return {Path("/"): -1}
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            try:
                pid = int(line[1:])
            except ValueError:
                pid = None
        elif line.startswith("n/") and pid is not None:
            try:
                observed[Path(line[1:]).resolve()] = pid
            except OSError:
                continue
    return observed


def foreign_worktree_occupant(worktree: Path) -> int | None:
    """pid of a live process OUTSIDE this process's own lineage with cwd at or under
    `worktree`; -1 when the probe was unavailable (fail closed: caller must not supersede);
    None when no foreign process occupies the worktree."""
    try:
        root = worktree.resolve()
    except OSError:
        return -1
    lineage = _ancestor_pids()
    for cwd, pid in _process_cwds().items():
        if pid == -1:
            return -1
        if pid in lineage:
            continue
        if cwd == root or root in cwd.parents:
            return pid
    return None
