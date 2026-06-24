import contextlib
import os
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import yaml

from limen.models import LimenFile

_DLOG_REQUIRED = {"timestamp", "agent", "session_id", "status"}


@contextlib.contextmanager
def queue_lock(tasks_path: Path, timeout: int = 90) -> Iterator[bool]:
    """Cross-process mutex on tasks.yaml writes — the CANONICAL home of the lock (dispatch.py's
    _queue_lock and heal-dispatch.py's acquire_lock are the same mkdir-mutex; this is the shared
    one every mutator should converge on so they can't drift). The lockdir is DERIVED from
    tasks_path (its sibling logs/.queue.lock.d) so production uses the same dir the heartbeat +
    dispatchers use ($LIMEN_ROOT/logs/.queue.lock.d), while a temp tasks.yaml in tests gets an
    isolated lock instead of blocking on the real repo's. Yields True if the lock was acquired,
    False on timeout — callers MUST honor a False by skipping their write (never block the beat,
    never dead-stop: a missed routing pass is harmless and self-corrects next beat)."""
    lockd = Path(tasks_path).parent / "logs" / ".queue.lock.d"
    got = False
    lockd.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(timeout):
        try:
            lockd.mkdir()
            got = True
            break
        except FileExistsError:
            time.sleep(1)
    try:
        yield got
    finally:
        if got:
            try:
                lockd.rmdir()
            except OSError:
                pass


def _sanitize_dispatch_logs(raw: object) -> int:
    """NEVER-"NO" data-layer guard: tolerate torn writes. The shared tasks.yaml is written by many
    uncoordinated processes; a recurring corruption lands a whole Task object inside some task's
    dispatch_log (an entry missing timestamp/agent/session_id), which made strict validation reject
    the ENTIRE 900+-task queue — silently breaking the generator, harvest, prune, and the daemon's
    own beats. Drop ONLY the malformed log entries (garbage history rows); every task + the queue
    survive. Mutates raw in place; returns the count dropped."""
    if not isinstance(raw, dict):
        return 0
    dropped = 0
    for t in raw.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        dl = t.get("dispatch_log")
        if not isinstance(dl, list):
            continue
        clean = [e for e in dl if isinstance(e, dict) and _DLOG_REQUIRED.issubset(e.keys())]
        dropped += len(dl) - len(clean)
        t["dispatch_log"] = clean
    return dropped


def load_limen_file(path: Path) -> LimenFile:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        # an empty/whitespace file is corruption, not an empty queue — refuse to load it as
        # None (which would crash downstream); the caller should restore from git/backup.
        raise ValueError(f"{path} is empty or invalid YAML — refusing to load (restore from git HEAD)")
    dropped = _sanitize_dispatch_logs(raw)
    if dropped:
        print(f"[limen.io] tolerated {dropped} malformed dispatch_log "
              f"entr{'y' if dropped == 1 else 'ies'} in {Path(path).name} (torn-write recovery)",
              file=sys.stderr)
    return LimenFile.model_validate(raw)


def atomic_write_text(path: Path, text: str) -> None:
    """Crash-/race-safe text write: serialize to a temp file in the same dir, fsync, then
    os.replace(). os.replace is atomic on POSIX, so a crash or a concurrent reader can NEVER
    observe a truncated/empty file — the race that emptied tasks.yaml to 0 bytes on 2026-06-19.
    This is the ONE writer primitive every tasks.yaml writer must route through (the heartbeat
    read None mid-write and went idle until this was unified)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_limen_file(path: Path, limen: LimenFile) -> None:
    data = limen.model_dump(mode="json", exclude_none=True)
    text = yaml.dump(data, sort_keys=False, default_flow_style=False)
    atomic_write_text(path, text)
