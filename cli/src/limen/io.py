import contextlib
import os
import re
import sys
import tempfile
import time
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from limen.models import LimenFile

_DLOG_REQUIRED = {"timestamp", "agent", "session_id", "status"}


class BoardCollapseError(RuntimeError):
    """Raised when a save would catastrophically shrink the board — a clobber. The existing
    good board is left INTACT and the rejected payload is preserved to a `.rejected-<stamp>`
    sidecar (never lost). See save_limen_file's collapse-guard."""


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
    if os.environ.get("LIMEN_QUEUE_LOCK_HELD") == "1" and lockd.exists():
        yield True
        return
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


def _sanitize_dispatch_logs(raw: dict[str, object]) -> int:
    """NEVER-"NO" data-layer guard: tolerate torn writes. The shared tasks.yaml is written by many
    uncoordinated processes; a recurring corruption lands a whole Task object inside some task's
    dispatch_log (an entry missing timestamp/agent/session_id), which made strict validation reject
    the ENTIRE 900+-task queue — silently breaking the generator, harvest, prune, and the daemon's
    own beats. Drop ONLY the malformed log entries (garbage history rows); every task + the queue
    survive. Mutates raw in place; returns the count dropped."""
    if not isinstance(raw, dict):
        return 0
    dropped = 0
    tasks = raw.get("tasks")
    if not isinstance(tasks, list):
        return 0
    for t in tasks:
        if not isinstance(t, dict):
            continue
        dl = t.get("dispatch_log")
        if not isinstance(dl, list):
            continue
        clean = [e for e in dl if isinstance(e, dict) and _DLOG_REQUIRED.issubset(e.keys())]
        dropped += len(dl) - len(clean)
        t["dispatch_log"] = clean
    return dropped


def _backfill_required_task_fields(raw: dict[str, object]) -> int:
    """NEVER-"NO" data-layer guard, second face: tolerate a task missing a required scalar
    (notably `created`). On 2026-06-26 a writer wrote a freshly-built task that lacked `created`;
    because `Task.created` is required, `model_validate` raised on the WHOLE board, so every
    daemon beat's load threw and the queue went idle for hours — one partial task nuked the entire
    institution. Backfill the field (from `updated`'s date-part, else today) instead of rejecting
    the board. Mutates raw in place; returns the count backfilled. Same philosophy as
    _sanitize_dispatch_logs — salvage the queue, never dead-stop."""
    if not isinstance(raw, dict):
        return 0
    today = date.today().isoformat()
    fixed = 0
    tasks = raw.get("tasks")
    if not isinstance(tasks, list):
        return 0
    for t in tasks:
        if not isinstance(t, dict):
            continue
        if not t.get("created"):
            upd = t.get("updated")
            t["created"] = str(upd)[:10] if upd else today
            fixed += 1
    return fixed


def load_limen_text(text: str, name: str = "tasks.yaml") -> LimenFile:
    """Parse a board from an in-memory string — the single-read entry point.

    Callers that must reason about the *exact bytes* they loaded (e.g. the materialize --verify
    byte-identity check, or history-replay loading a git revision) read the file once and pass the
    buffer here, instead of reading it a second time — a live board the fleet rewrites every beat
    can change between two reads (a TOCTOU false-negative). `load_limen_file` is this plus the read.
    """
    raw = yaml.safe_load(text)
    if raw is None:
        # an empty/whitespace file is corruption, not an empty queue — refuse to load it as
        # None (which would crash downstream); the caller should restore from git/backup.
        raise ValueError(f"{name} is empty or invalid YAML — refusing to load (restore from git HEAD)")
    dropped = _sanitize_dispatch_logs(raw)
    if dropped:
        print(
            f"[limen.io] tolerated {dropped} malformed dispatch_log "
            f"entr{'y' if dropped == 1 else 'ies'} in {name} (torn-write recovery)",
            file=sys.stderr,
        )
    backfilled = _backfill_required_task_fields(raw)
    if backfilled:
        print(
            f"[limen.io] backfilled missing `created` on {backfilled} "
            f"task{'' if backfilled == 1 else 's'} in {name} (one partial task must "
            f"never reject the whole board)",
            file=sys.stderr,
        )
    return LimenFile.model_validate(raw)


def load_limen_file(path: Path) -> LimenFile:
    return load_limen_text(path.read_text(), name=Path(path).name)


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


def _ondisk_task_count(path: Path) -> int:
    """Cheap, parse-free count of the tasks already on disk: every task item begins with a
    `- id:` line and nothing else does (dispatch_log rows start with `- timestamp:`). Returns 0
    if the file is missing/unreadable — the guard only fires when a SUBSTANTIAL prior board is
    provably present, so an unknown prior never blocks a legitimate (re)write or a fresh bootstrap."""
    try:
        return len(re.findall(r"(?m)^\s*- id:", Path(path).read_text()))
    except (OSError, UnicodeDecodeError):
        return 0


def _board_guard_config() -> tuple[bool, int, float]:
    """(enabled, floor, fraction) — declared in institutio/governance/parameters.yaml as
    LIMEN_BOARD_GUARD / LIMEN_BOARD_SHRINK_FLOOR / LIMEN_BOARD_SHRINK_FRACTION."""
    on = os.environ.get("LIMEN_BOARD_GUARD", "1") != "0"
    try:
        floor = int(os.environ.get("LIMEN_BOARD_SHRINK_FLOOR", "5"))
    except ValueError:
        floor = 5
    try:
        fraction = float(os.environ.get("LIMEN_BOARD_SHRINK_FRACTION", "0.10"))
    except ValueError:
        fraction = 0.10
    return on, floor, fraction


def save_limen_file(path: Path, limen: LimenFile, *, allow_shrink: bool = False) -> None:
    path = Path(path)
    data = limen.model_dump(mode="json", exclude_none=True)
    text = yaml.dump(data, sort_keys=False, default_flow_style=False)

    # COLLAPSE-GUARD — the choke point. On 2026-06-26 a writer atomically replaced the live
    # 1449-task queue with a single freshly-built task, halting the whole institution (every beat
    # then loaded 1 task → idle). The board only ever GROWS or holds steady: all save callers
    # load→mutate→save and terminal tasks are retained, so a catastrophic shrink toward zero is
    # ALWAYS a bug, never legitimate. Refuse it, preserve the rejected payload to a sidecar (never
    # lost), and leave the good board intact. `allow_shrink=True` is the explicit escape hatch for
    # an intentional bulk archive/prune; LIMEN_BOARD_GUARD=0 disables the guard entirely.
    guard_on, floor, fraction = _board_guard_config()
    if guard_on and not allow_shrink:
        prior = _ondisk_task_count(path)
        new_count = len(limen.tasks)
        threshold = max(floor, int(prior * fraction))
        if prior > floor and new_count < threshold:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            sidecar = path.with_name(f"{path.name}.rejected-{stamp}")
            with contextlib.suppress(OSError):
                atomic_write_text(sidecar, text)
            raise BoardCollapseError(
                f"refusing to shrink {path.name} from {prior} tasks to {new_count} "
                f"(< {threshold} = max({floor}, {fraction:g}×prior)); rejected payload preserved "
                f"to {sidecar.name}. Pass allow_shrink=True for an intentional bulk archive, "
                f"or set LIMEN_BOARD_GUARD=0 to disable."
            )

    atomic_write_text(path, text)
