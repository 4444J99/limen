"""TABVLARIVS — the one record-keeper over the board (`tasks.yaml`).

The disease this dissolves: ~32 uncoordinated writers each do *read-whole-board → mutate →
rewrite-whole-board* on the single `tasks.yaml` blob. `io.atomic_write_text` already stops torn
*bytes* (temp-file + `os.replace`), but two writers that both `load→save` still lost-update-clobber
(last-writer-wins on the whole board), and the worst offenders (the MCP server) skip even the
atomic write. Locking every `save` would give write-*atomicity* but not read-modify-write
*isolation* — the clobber survives. The only correct cure is the **single-writer principle**:
workers stop mutating shared state and instead APPEND one immutable *ticket* per unit of work to a
lock-free inbox; exactly **one** keeper drains the inbox, folds the tickets onto the board in
timestamp order, validates (per-task + the collapse-guard), and seals the result with the atomic
write. It is the only process that ever holds the write lock, so there is no interleave to tear.

This is Step 2+3 of `board-is-event-log-projection` (PR#543): `materialize.fold` is the proven pure
reducer — this module gives it a live stream to consume. A ticket **is** a `materialize` Event with
provenance (who did the work, when), and the archived ticket files are the append-only event log
that the board is a projection of (`board = fold(events)`).

Ticket lifecycle::

    logs/tickets/inbox/<id>.json  --drain-->  applied → archive/   (the event log)
                                              rejected → rejected/  (+ <id>.reason.txt)

Design invariants (each carried over from a shipped safety precedent):
  * **A worker never touches `tasks.yaml`.** It calls `submit_ticket`, an exclusive atomic create
    into the inbox — no read, no lock, no collapse risk, no interleave. (Preserves the one writer
    the fleet must never starve, `ingest-backlog.py`, which deliberately skipped the lock.)
  * **One bad ticket never rejects the batch.** Each ticket is applied + validated individually;
    a bad one is quarantined to `rejected/` and the rest still land (the `_sanitize_dispatch_logs`
    tolerate-and-salvage philosophy from `io.py`).
  * **The seal is collapse-guarded.** The board is written through `save_limen_file`, so the
    2026-06-26 shrink-to-1 clobber remains impossible; a batch that would collapse the board is
    rejected whole and the good board is left intact.
  * **Never dead-stop the beat.** If the queue lock is held (a legacy writer, mid-migration), the
    keeper defers to the next beat rather than blocking — exactly like `heal-board.py`.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from limen.io import BoardCollapseError, load_limen_file, queue_lock, save_limen_file
from limen.materialize import EV_BOARD_META, EV_BOARD_ORDER, EV_TASK_UPSERT, Event, fold
from limen.models import Task

# --- ticket intents (a superset of materialize's Event tags, plus the status convenience) --------
INTENT_UPSERT = "task.upsert"  # create-or-merge a task field-set (patch may be full or partial)
INTENT_STATUS = "task.status"  # the common worker ticket: set status + append a dispatch_log entry
INTENT_REMOVE = "task.remove"  # drop a task id (prune/archive-out)
INTENT_ORDER = "board.order"  # set the task display order (patch = {"ids": [...]})
INTENT_META = "board.meta"  # set board version/portal (patch = {"version":..,"portal":..})
_INTENTS = frozenset({INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE, INTENT_ORDER, INTENT_META})


class Ticket(BaseModel):
    """One immutable unit of board work a worker hands to the record-keeper.

    A worker builds a Ticket describing the transition it performed ("here's the work I did") and
    drops it into the inbox via `submit_ticket`. It is an Event with provenance — the `patch` is a
    *field-level delta*, never a whole-board rewrite, so a torn ticket can at worst be quarantined
    and never corrupts the SSOT.
    """

    ticket_id: str
    timestamp: datetime
    agent: str
    session_id: str = "unknown"
    intent: str
    task_id: str | None = None
    # field-level delta: for upsert/status the task field-patch; for board.order {"ids": [...]};
    # for board.meta {"version": .., "portal": ..}.
    patch: dict[str, Any] | None = None
    # optional dispatch_log payload appended to the task's log — {"status": .., "output"?: ..}.
    log: dict[str, Any] | None = None


def new_ticket_id(session_id: str = "unknown", now: datetime | None = None) -> str:
    """A sortable, collision-free ticket id: `<utc-timestamp>-<session>-<rand>`. The timestamp
    prefix makes a plain filename sort chronological (the keeper's drain order), and the random
    tail guarantees two tickets from the same session in the same microsecond never collide."""
    now = now or datetime.now(timezone.utc)
    safe_session = "".join(c if c.isalnum() or c in "._-" else "_" for c in session_id)[:40]
    return f"{now.strftime('%Y%m%dT%H%M%S_%f')}Z-{safe_session}-{uuid.uuid4().hex[:8]}"


# --- inbox geometry ------------------------------------------------------------------------------
def tickets_root(board_path: Path) -> Path:
    return Path(board_path).parent / "logs" / "tickets"


def _inbox(board_path: Path) -> Path:
    return tickets_root(board_path) / "inbox"


def _archive(board_path: Path) -> Path:
    return tickets_root(board_path) / "archive"


def _rejected(board_path: Path) -> Path:
    return tickets_root(board_path) / "rejected"


def submit_ticket(board_path: Path, ticket: Ticket) -> Path:
    """Append a ticket to the inbox — the worker's *only* board-write surface.

    Exclusive + atomic: write to a temp file, fsync, then `os.link` it into place. `os.link` fails
    if the destination exists, so a duplicate `ticket_id` raises instead of clobbering, and a reader
    can never observe a half-written ticket. No lock, no board read — many workers submit
    concurrently without contending.
    """
    if ticket.intent not in _INTENTS:
        raise ValueError(f"unknown ticket intent: {ticket.intent!r}")
    inbox = _inbox(board_path)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f"{ticket.ticket_id}.json"
    fd, tmp = tempfile.mkstemp(dir=inbox, prefix=f".{ticket.ticket_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ticket.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)  # atomic exclusive create — raises FileExistsError on a duplicate id
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return dest


def submit_task_upsert(
    board_path: Path,
    task: "Task | dict[str, Any]",
    *,
    agent: str,
    session_id: str = "unknown",
    now: datetime | None = None,
) -> Path:
    """One-line producer: hand the keeper a whole task field-set as an upsert ticket.

    This is the conversion target for every writer that used to `load → extend → save_limen_file`.
    A generator/miner drops the ``save_limen_file`` and instead calls this once per NEW task; the
    keeper folds it onto the board on the next beat. The full field-set becomes the ticket ``patch``.

    The task is validated HERE (fail-fast, exactly like the old ``Task(**t)`` before a direct write),
    so a producer never emits an invalid task — the keeper's per-ticket validation stays a second
    line of defense, not the first. Dedup remains the caller's responsibility: read the board and
    submit only genuinely-new ids, because an upsert MERGES onto any existing task ({**base, **patch})
    and blind-upserting a live id would overwrite its fields (e.g. flip a `done` task back to `open`).
    """
    validated = task if isinstance(task, Task) else Task.model_validate(task)
    fields = validated.model_dump(mode="json", exclude_none=True)
    tid = fields.get("id")
    if not tid:
        raise ValueError("task upsert requires an 'id'")
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_UPSERT,
        task_id=tid,
        patch=fields,
    )
    return submit_ticket(board_path, ticket)


@dataclass
class DrainResult:
    """The outcome of one drain pass — counts only (safe to log)."""

    pending: int = 0
    applied: int = 0
    rejected: int = 0
    wrote: bool = False
    deferred: bool = False
    note: str = ""
    applied_ids: list[str] = field(default_factory=list)
    rejected_ids: list[str] = field(default_factory=list)


def pending_count(board_path: Path) -> int:
    inbox = _inbox(board_path)
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def _parse_pending(inbox: Path) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Load every inbox ticket, splitting parseable from garbage, then order the good ones by
    (timestamp, id) so concurrent submissions replay in a single deterministic total order."""
    good: list[tuple[Path, Ticket]] = []
    bad: list[tuple[Path, str]] = []
    for p in sorted(inbox.glob("*.json")):
        try:
            good.append((p, Ticket.model_validate_json(p.read_text())))
        except Exception as exc:  # a torn/invalid ticket is quarantined, never fatal
            bad.append((p, f"unparseable/invalid ticket: {exc}"))
    good.sort(key=lambda pt: (pt[1].timestamp, pt[1].ticket_id))
    return good, bad


def _apply(ticket: Ticket, tasks: OrderedDict[str, dict[str, Any]], meta: dict[str, Any]) -> None:
    """Fold one ticket onto the in-memory board state (mutates `tasks`/`meta` in place).

    Validates the resulting single task so a malformed ticket raises HERE and is quarantined alone,
    rather than failing the whole-board validation at seal time and taking good tickets down with it.
    """
    if ticket.intent == INTENT_REMOVE:
        if not ticket.task_id:
            raise ValueError("task.remove requires task_id")
        tasks.pop(ticket.task_id, None)
        return

    if ticket.intent in (INTENT_UPSERT, INTENT_STATUS):
        if not ticket.task_id:
            raise ValueError(f"{ticket.intent} requires task_id")
        base = dict(tasks.get(ticket.task_id, {}))
        merged = {**base, **(ticket.patch or {})}
        merged["id"] = ticket.task_id
        merged["updated"] = ticket.timestamp.isoformat()
        if ticket.log:
            status = ticket.log.get("status") or merged.get("status")
            entry = {
                "timestamp": ticket.timestamp.isoformat(),
                "agent": ticket.agent,
                "session_id": ticket.session_id,
                "status": status,
                "output": ticket.log.get("output"),
            }
            merged["dispatch_log"] = list(base.get("dispatch_log", [])) + [entry]
            # a task.status ticket carries the transition in its log payload; honor it as the status
            if ticket.intent == INTENT_STATUS and "status" not in (ticket.patch or {}) and status:
                merged["status"] = status
        Task.model_validate(merged)  # reject a bad ticket individually
        tasks[ticket.task_id] = merged  # dict update keeps first-seen position; new id appends
        return

    if ticket.intent == INTENT_META:
        p = ticket.patch or {}
        if "version" in p:
            meta["version"] = p["version"]
        if "portal" in p:
            meta["portal"] = p["portal"]
        return

    if ticket.intent == INTENT_ORDER:
        meta["order"] = list((ticket.patch or {}).get("ids", []))
        return

    raise ValueError(f"unknown ticket intent: {ticket.intent!r}")


def _move(paths: list[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        try:
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _quarantine(rejected: list[tuple[Path, str]], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p, reason in rejected:
        try:
            (dest_dir / f"{p.name}.reason.txt").write_text(reason)
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def drain_once(board_path: Path, *, dry_run: bool = False, lock_timeout: int = 20) -> DrainResult:
    """Drain the inbox once: fold every pending ticket onto the board, seal, archive.

    The whole load→fold→seal runs under the queue lock, and the keeper is the only drainer, so there
    is no read-modify-write race. An empty inbox is an instant no-op (no lock, no board I/O) — which
    is what makes it safe to run every beat while no producers exist yet.
    """
    board_path = Path(board_path)
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return DrainResult(note="inbox empty")

    good, bad = _parse_pending(inbox)
    pending = len(good) + len(bad)
    if pending == 0:
        return DrainResult(note="inbox empty")

    if dry_run:
        return DrainResult(
            pending=pending,
            applied=len(good),
            rejected=len(bad),
            note=f"dry-run: {len(good)} applicable, {len(bad)} unparseable",
        )

    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return DrainResult(pending=pending, deferred=True, note="queue lock held; deferred to next beat")

        board = load_limen_file(board_path)
        board_json = board.model_dump(mode="json", exclude_none=True)
        tasks: OrderedDict[str, dict[str, Any]] = OrderedDict((t["id"], t) for t in board_json.get("tasks", []))
        meta: dict[str, Any] = {"version": board_json.get("version", "1.0"), "portal": board_json.get("portal")}

        applied: list[tuple[Path, Ticket]] = []
        rejected: list[tuple[Path, str]] = list(bad)
        for p, ticket in good:
            try:
                _apply(ticket, tasks, meta)
                applied.append((p, ticket))
            except Exception as exc:
                rejected.append((p, f"apply failed: {exc}"))

        wrote = False
        if applied:
            events: list[Event] = [
                {"type": EV_BOARD_META, "data": {"version": meta["version"], "portal": meta["portal"]}}
            ]
            for tid, fields in tasks.items():
                events.append({"type": EV_TASK_UPSERT, "task_id": tid, "data": fields})
            if meta.get("order"):
                events.append({"type": EV_BOARD_ORDER, "data": {"ids": meta["order"]}})
            try:
                new_board = fold(events)  # the proven reducer assembles + validates the whole board
                save_limen_file(board_path, new_board)  # collapse-guard + atomic seal
                wrote = True
            except BoardCollapseError as exc:
                # the batch would collapse the board — never write; quarantine it whole, board intact
                rejected.extend((p, f"batch rejected by collapse-guard: {exc}") for p, _ in applied)
                applied = []

        _move([p for p, _ in applied], _archive(board_path))
        _quarantine(rejected, _rejected(board_path))

    return DrainResult(
        pending=pending,
        applied=len(applied),
        rejected=len(rejected),
        wrote=wrote,
        note=("sealed" if wrote else "no board change"),
        applied_ids=[t.ticket_id for _, t in applied],
        rejected_ids=[p.stem for p, _ in rejected],
    )
