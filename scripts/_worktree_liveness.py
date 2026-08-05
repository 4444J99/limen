"""_worktree_liveness — is a live process working inside this directory? One probe, two consumers.

Extracted VERBATIM from reclaim-worktrees.py (the SPRAWL-RECLAIM organ), where it is what kept two
live interactive sessions from being reclaimed on 2026-07-29 while 7 dead worktrees around them
were taken. The second consumer is check-session-streams.py, which needs the OPPOSITE decision
from the same fact: reclaim must not delete a live worktree; the stream launcher must not reopen
one — and must reopen a dormant one, which the old directory-existence test made impossible (a
stream that had been opened once could never re-enter the ready set).

FAIL-CLOSED, and that is the correct direction for BOTH consumers: when the probe itself is
unavailable, every directory reports a live owner (pid -1), so reclaim declines to delete and the
launcher declines to reopen. A broken probe can only under-act, never destroy or double-open.

The scan is memoized module-wide (`process_owner`): N streams cost one `lsof`, and the CI gate that
never asks the question never pays for the scan at all. `reclaim-worktrees.py` manages its own
refresh cycle instead (it re-scans mid-apply on purpose) and calls `active_process_cwds()` direct.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def active_process_cwds() -> dict[Path, int]:
    """Return observable process cwd roots; an unavailable probe fails closed."""
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
        result = subprocess.run(
            ["lsof", "-n", "-a", "-d", "cwd", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
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


def owner_in(cwds: dict[Path, int], d: Path) -> int | None:
    """The containment rule, shared verbatim: a process owns `d` when its cwd IS `d` or sits
    anywhere beneath it. The fail-closed sentinel (pid -1) owns everything."""
    try:
        root = d.resolve()
    except OSError:
        return -1
    for cwd, pid in cwds.items():
        if pid == -1:
            return -1
        if cwd == root or root in cwd.parents:
            return pid
    return None


_MEMO: dict[Path, int] | None = None


def process_owner(d: Path, *, refresh: bool = False) -> int | None:
    """pid of a live process with cwd at or under `d`; -1 when the probe was unavailable
    (fail-closed); None when nothing is attached. One scan per process, unless refreshed."""
    global _MEMO
    if _MEMO is None or refresh:
        _MEMO = active_process_cwds()
    return owner_in(_MEMO, d)
