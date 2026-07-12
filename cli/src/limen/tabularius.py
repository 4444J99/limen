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
import subprocess
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from limen.intake import validate_intake_contract
from limen.io import BoardCollapseError, load_limen_file, queue_lock, save_limen_file
from limen.materialize import EV_BOARD_META, EV_BOARD_ORDER, EV_TASK_UPSERT, Event, fold
from limen.models import LimenFile, Task

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
    validate_intake_contract(validated, is_new=True)
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


@dataclass
class PreserveResult:
    changed: bool = False
    pushed: bool = False
    deferred: bool = False
    skipped: bool = False
    reason: str = ""
    commit: str = ""


def pending_count(board_path: Path) -> int:
    inbox = _inbox(board_path)
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def pending_upsert_patches(board_path: Path) -> list[dict[str, Any]]:
    """Return valid pending upsert patches without mutating the board.

    Producers use this as a read-side dedup hint: a task can be absent from the board but already
    waiting in the keeper inbox. Malformed tickets are ignored here; the drain pass owns quarantine.
    """
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return []
    patches: list[dict[str, Any]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            ticket = Ticket.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if ticket.intent == INTENT_UPSERT and isinstance(ticket.patch, dict):
            patches.append(ticket.patch)
    return patches


def pending_task_ids(board_path: Path) -> set[str]:
    ids: set[str] = set()
    for patch in pending_upsert_patches(board_path):
        tid = patch.get("id")
        if isinstance(tid, str) and tid:
            ids.add(tid)
    return ids


def _git(repo: Path, args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _short_output(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:220]


def _commit_identity_env(repo: Path, env: dict[str, str]) -> dict[str, str]:
    """Provide commit-tree identity defaults without mutating repo git config."""
    identity = dict(env)
    name = _git(repo, ["config", "user.name"], env=env).stdout.strip() or "Limen Tabularius"
    email = _git(repo, ["config", "user.email"], env=env).stdout.strip() or "tabularius@limen.local"
    identity.setdefault("GIT_AUTHOR_NAME", os.environ.get("GIT_AUTHOR_NAME", name))
    identity.setdefault("GIT_AUTHOR_EMAIL", os.environ.get("GIT_AUTHOR_EMAIL", email))
    identity.setdefault("GIT_COMMITTER_NAME", os.environ.get("GIT_COMMITTER_NAME", name))
    identity.setdefault("GIT_COMMITTER_EMAIL", os.environ.get("GIT_COMMITTER_EMAIL", email))
    return identity


def preserve_board_projection(
    board_path: Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    dry_run: bool = False,
    lock_timeout: int = 2,
) -> PreserveResult:
    """Commit and push the board projection as a Tabularius-owned action.

    This is not a second writer. It never edits `tasks.yaml`; it preserves the current projection
    after the record-keeper has sealed it. The commit is built from a temporary index and pushed
    before the local branch is advanced, so a push failure cannot strand the live checkout ahead.
    """
    board_path = Path(board_path)
    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return PreserveResult(deferred=True, reason="queue-lock-held")

        top = _git(board_path.parent, ["rev-parse", "--show-toplevel"])
        if top.returncode != 0 or not top.stdout.strip():
            return PreserveResult(skipped=True, reason="not-a-git-repo")
        repo = Path(top.stdout.strip())
        try:
            rel_board = board_path.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return PreserveResult(skipped=True, reason="board-outside-git-root")

        status = _git(repo, ["status", "--porcelain", "--", rel_board])
        if status.returncode != 0:
            return PreserveResult(skipped=True, reason=f"status-failed:{_short_output(status)}")
        if not status.stdout.strip():
            return PreserveResult(skipped=True, reason="no-board-changes")
        if dry_run:
            return PreserveResult(changed=True, skipped=True, reason=f"would-preserve:{rel_board}")

        current = _git(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"])
        if current.returncode != 0 or current.stdout.strip() != branch:
            return PreserveResult(skipped=True, reason=f"not-on-{branch}")
        fetch = _git(repo, ["fetch", "--quiet", remote, branch])
        if fetch.returncode != 0:
            return PreserveResult(skipped=True, reason=f"fetch-failed:{_short_output(fetch)}")
        head = _git(repo, ["rev-parse", "HEAD"]).stdout.strip()
        remote_ref = f"{remote}/{branch}"
        remote_sha = _git(repo, ["rev-parse", remote_ref]).stdout.strip()
        if not head or head != remote_sha:
            return PreserveResult(changed=True, skipped=True, reason=f"not-at-{remote_ref}")

        with tempfile.NamedTemporaryFile(prefix="tabularius-board-index-") as tmp:
            env = {"GIT_INDEX_FILE": tmp.name}
            read_tree = _git(repo, ["read-tree", "HEAD"], env=env)
            if read_tree.returncode != 0:
                return PreserveResult(changed=True, skipped=True, reason=f"read-tree-failed:{_short_output(read_tree)}")
            add = _git(repo, ["add", "-A", "--", rel_board], env=env)
            if add.returncode != 0:
                return PreserveResult(changed=True, skipped=True, reason=f"add-failed:{_short_output(add)}")
            # DATA_ONLY invariant (issue #872 / PREC-2026-07-10-direct-push-lane-rots-main): tabularius
            # pushes the board projection to `main` directly — it must NEVER carry anything but the board
            # itself. Make that executable: fail LOUD if the temp index ever holds any other path.
            staged = _git(repo, ["diff", "--cached", "--name-only"], env=env)
            staged_paths = {line.strip() for line in staged.stdout.splitlines() if line.strip()}
            if not staged_paths <= {rel_board}:
                raise AssertionError(
                    f"tabularius board push would carry non-board paths {sorted(staged_paths - {rel_board})}; "
                    "the DATA_ONLY invariant (only tasks.yaml may reach main via this lane) was violated"
                )
            diff = _git(repo, ["diff", "--cached", "--quiet", "--", rel_board], env=env)
            if diff.returncode == 0:
                return PreserveResult(skipped=True, reason="no-index-diff")
            tree = _git(repo, ["write-tree"], env=env)
            if tree.returncode != 0 or not tree.stdout.strip():
                return PreserveResult(changed=True, skipped=True, reason=f"write-tree-failed:{_short_output(tree)}")
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            commit = _git(
                repo,
                [
                    "commit-tree",
                    tree.stdout.strip(),
                    "-p",
                    head,
                    "-m",
                    f"tabularius: preserve board projection {stamp}",
                ],
                env=_commit_identity_env(repo, env),
            )
            if commit.returncode != 0 or not commit.stdout.strip():
                return PreserveResult(changed=True, skipped=True, reason=f"commit-tree-failed:{_short_output(commit)}")
            commit_sha = commit.stdout.strip()

        push = _git(repo, ["push", remote, f"{commit_sha}:refs/heads/{branch}"])
        if push.returncode != 0:
            return PreserveResult(changed=True, skipped=True, reason=f"push-failed:{_short_output(push)}")

        _git(repo, ["update-ref", f"refs/heads/{branch}", commit_sha, head])
        _git(repo, ["update-ref", f"refs/remotes/{remote_ref}", commit_sha, remote_sha])
        _git(repo, ["reset", "-q", "--", rel_board])
        return PreserveResult(changed=True, pushed=True, commit=commit_sha)


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
        is_new = ticket.task_id not in tasks
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
        validated = Task.model_validate(merged)  # reject a bad ticket individually
        # A caller can bypass ``submit_task_upsert`` by constructing a raw Ticket.
        # The keeper repeats admission independently so that ticket is quarantined
        # alone while valid siblings still land.
        validate_intake_contract(validated, is_new=is_new)
        tasks[ticket.task_id] = merged  # dict update keeps first-seen position; new id appends
        return

    if ticket.intent == INTENT_META:
        p = ticket.patch or {}
        candidate = dict(meta)
        if "version" in p:
            candidate["version"] = p["version"]
        if "portal" in p:
            if p["portal"] is not None and not isinstance(p["portal"], dict):
                raise ValueError("board.meta portal must be a mapping")
            candidate["portal"] = p["portal"]
        LimenFile.model_validate(
            {
                "version": candidate.get("version", "1.0"),
                "portal": candidate.get("portal"),
                "tasks": list(tasks.values()),
            }
        )
        meta.clear()
        meta.update(candidate)
        return

    if ticket.intent == INTENT_ORDER:
        ids = (ticket.patch or {}).get("ids", [])
        if not isinstance(ids, list) or any(not isinstance(tid, str) for tid in ids):
            raise ValueError("board.order ids must be a list of task id strings")
        meta["order"] = list(ids)
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
            except Exception as exc:
                rejected.extend((p, f"batch rejected by board validation: {exc}") for p, _ in applied)
                applied = []
            else:
                try:
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
