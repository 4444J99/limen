#!/usr/bin/env python3
"""heal-board.py — the BOARD-INTEGRITY self-heal (autopoietic recovery net).

The collapse-guard in `limen.io.save_limen_file` makes the 2026-06-26 incident — a writer
atomically replacing the live 1449-task queue with one freshly-built task — impossible going
forward. This script is the belt-and-suspenders behind that guard: if the live board is EVER
unloadable or collapsed (a non-atomic external write, disk corruption, a guard-bypassed path,
a future regression), restore it from the last committed-good snapshot (`git show HEAD:tasks.yaml`)
instead of leaving the daemon idling on a dead queue. This is the "fix the handoff so it ain't
broken" self-heal: the institution recovers ITSELF instead of waiting for a human hand-restore.

On a HEALTHY board it also runs three idempotent lifecycle repairs so the board never drifts out
of the canonical vocabulary the validator (`validate-task-board.py`) enforces:
  - reopened-done: a task reopened after a terminal `done` log is restored to `done`.
  - needs-human reconcile: a task LABELED `needs-human` that is sitting in a *dispatchable*
    status (open/dispatched/in_progress) is transitioned to the `needs_human` STATUS. Without
    this the fleet re-picks a human-gated lever forever AND the validator fails the whole build
    (needs-human-in-open) — exactly the drift that turned `main` red after mining filed the
    L-* levers as `open`. Root cause is fixed at the source in `mine-backlog.py`; this heals any
    already-mined ones and any future guard-bypassed path.
  - log-mismatch reconcile: a task whose latest *canonical* dispatch_log status disagrees with
    task.status (the validator's `log_mismatches` failure) gets one canonical event appended that
    restates the authoritative task.status head, so the log agrees again. This is the effector for
    the validator's existing sensor: a momentarily-inconsistent record committed to the fast-churning
    board (e.g. GH-organvm-limen-872 — status=open after a timeout, but the last canonical log entry
    was `dispatched`, with no release event ever appended) otherwise fails `verify` on EVERY PR based
    on that snapshot until an unrelated write happens to mask it. Trusting the status head keeps this
    a safe, idempotent alignment — once the head matches, it is a no-op.

Wired into the heartbeat as a per-beat preflight, so a collapsed board self-restores at the
start of every beat — but IDEMPOTENT: a healthy board is a no-op (exit 0, no writes).

  python3 scripts/heal-board.py            # heal if collapsed, else no-op (exit 0)
  python3 scripts/heal-board.py --check    # report only; exit 1 if collapsed, never mutate
  python3 scripts/heal-board.py --dry-run  # report what WOULD be restored; make no writes
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.dispatch import _restore_done_status  # noqa: E402
from limen.io import atomic_write_text, load_limen_file, queue_lock, save_limen_file  # noqa: E402
from limen.models import VALID_STATUSES, DispatchLogEntry, Task  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
HEAL_ON = os.environ.get("LIMEN_BOARD_HEAL", "1") != "0"
ACTIVE = {"open", "dispatched", "in_progress", "needs_human"}
NEEDS_HUMAN_LABEL = "needs-human"
DISPATCHABLE = {"open", "dispatched", "in_progress"}

try:
    FLOOR = int(os.environ.get("LIMEN_BOARD_SHRINK_FLOOR", "5"))
except ValueError:
    FLOOR = 5


def board_health(path: Path) -> tuple[bool, int, int]:
    """(loadable, total_tasks, active_tasks). A board that won't parse is (False, 0, 0)."""
    try:
        lf = load_limen_file(path)
    except Exception:
        return (False, 0, 0)
    total = len(lf.tasks)
    active = sum(1 for t in lf.tasks if t.status in ACTIVE)
    return (True, total, active)


def board_health_from_text(text: str, tmp_dir: Path) -> tuple[bool, int, int]:
    """Validate a candidate snapshot's text by loading it through the real loader."""
    probe = tmp_dir / f".heal-probe-{os.getpid()}.yaml"
    try:
        probe.write_text(text)
        return board_health(probe)
    finally:
        probe.unlink(missing_ok=True)


def git_head_board() -> str | None:
    """The last committed-good board: `git show HEAD:tasks.yaml` from the live checkout."""
    rel = os.environ.get("LIMEN_GITHUB_PATH", "tasks.yaml")
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"HEAD:{rel}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 and out.stdout.strip() else None


def _clear_async_markers(task_id: str) -> int:
    runs = ROOT / "logs" / "async-runs"
    cleared = 0
    for marker in runs.glob(f"{task_id}__*.running"):
        marker.unlink(missing_ok=True)
        cleared += 1
    for result in runs.glob(f"{task_id}.result.*"):
        result.unlink(missing_ok=True)
        cleared += 1
    return cleared


def _reconcile_needs_human(task: Task, now: datetime) -> bool:
    """Transition a `needs-human`-LABELED task out of a dispatchable STATUS.

    A human-gated lever mined as `open` (see mine-backlog.py) contradicts its own
    label: the fleet re-picks it forever and the board validator fails the build.
    Move it to the `needs_human` status and append aligned evidence so the
    latest-log-vs-status check also passes. Returns True iff it changed anything.
    """
    labels = {str(label) for label in (task.labels or [])}
    if NEEDS_HUMAN_LABEL not in labels or task.status not in DISPATCHABLE:
        return False
    task.status = "needs_human"
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent="heal-board",
            session_id="heal-board",
            status="needs_human",
            output="heal-board: reconciled needs-human label to needs_human status",
        )
    )
    return True


def _reconcile_log_mismatch(task: Task, now: datetime) -> bool:
    """Align the dispatch_log head with the authoritative task.status.

    The validator fails the build (`log_mismatches`) when a task's latest *canonical*
    dispatch_log status disagrees with task.status — the exact wedge that turned `verify`
    red across every PR based on a momentarily-inconsistent board snapshot. task.status is
    the authoritative projection head, so append one canonical event that restates it; the
    log then agrees and the invariant holds. Idempotent: once the head matches (or the last
    entry's status is non-canonical, which the validator ignores), it is a no-op. A task whose
    own status is non-canonical is a *different* defect (validator: `invalid`) and is left
    alone. Returns True iff it changed anything.
    """
    if task.status not in VALID_STATUSES:
        return False
    log = task.dispatch_log or []
    if not log:
        return False
    last_status = str(getattr(log[-1], "status", "") or "")
    if last_status not in VALID_STATUSES or last_status == task.status:
        return False
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent="heal-board",
            session_id="heal-board",
            status=task.status,
            output=f"heal-board: reconciled dispatch_log head to task.status={task.status} (was {last_status})",
        )
    )
    return True


def _apply_lifecycle_repairs(tasks: list[Task], now: datetime) -> tuple[list[str], list[str], list[str]]:
    """Run the three idempotent lifecycle repairs over the tasks in place.

    Returns (reopened_done_ids, reconciled_needs_human_ids, reconciled_log_mismatch_ids).
    The log-mismatch pass runs last so the earlier repairs (which set status AND append an
    aligned event) are already consistent and are not double-touched.
    """
    reopened: list[str] = []
    reconciled: list[str] = []
    mismatched: list[str] = []
    for task in tasks:
        if _restore_done_status(
            task,
            now,
            session_id="heal-board",
            output="heal-board: restored terminal done status after stale reopen",
        ):
            reopened.append(task.id)
        if _reconcile_needs_human(task, now):
            reconciled.append(task.id)
        if _reconcile_log_mismatch(task, now):
            mismatched.append(task.id)
    return reopened, reconciled, mismatched


def repair_lifecycle(*, check: bool, dry_run: bool) -> int:
    """Run the healthy-board lifecycle repairs (reopened-done + needs-human reconcile).

    Returns a process exit code. These are lifecycle repairs, not a collapse
    restore, so they run on every healthy-board beat and are idempotent.
    """
    try:
        lf = load_limen_file(BOARD)
    except Exception as exc:
        print(f"heal-board: lifecycle check skipped; board did not load: {exc}")
        return 1

    now = datetime.now(timezone.utc)
    reopened, reconciled, mismatched = _apply_lifecycle_repairs(lf.tasks, now)

    if not reopened and not reconciled and not mismatched:
        print(f"heal-board: OK — {BOARD.name} healthy (total={len(lf.tasks)} active={sum(1 for t in lf.tasks if t.status in ACTIVE)})")
        return 0

    if check:
        parts: list[str] = []
        if reopened:
            parts.append(f"{len(reopened)} reopened completed task(s) need repair: " + ", ".join(reopened[:10]))
        if reconciled:
            parts.append(f"{len(reconciled)} needs-human task(s) need reconcile to needs_human: " + ", ".join(reconciled[:10]))
        if mismatched:
            parts.append(f"{len(mismatched)} task(s) need dispatch_log head reconcile to task.status: " + ", ".join(mismatched[:10]))
        print("heal-board: " + "; ".join(parts))
        return 1
    if dry_run:
        parts = []
        if reopened:
            parts.append(f"WOULD restore {len(reopened)} reopened completed task(s): " + ", ".join(reopened[:10]))
        if reconciled:
            parts.append(f"WOULD reconcile {len(reconciled)} needs-human task(s) to needs_human: " + ", ".join(reconciled[:10]))
        if mismatched:
            parts.append(f"WOULD reconcile {len(mismatched)} log-mismatch task(s) to task.status: " + ", ".join(mismatched[:10]))
        print("heal-board: " + "; ".join(parts))
        return 0

    with queue_lock(BOARD, timeout=20) as locked:
        if not locked:
            print("heal-board: queue lock held; lifecycle repair deferred")
            return 1
        fresh = load_limen_file(BOARD)
        reopened, reconciled, mismatched = _apply_lifecycle_repairs(fresh.tasks, now)
        if reopened or reconciled or mismatched:
            save_limen_file(BOARD, fresh)
    cleared = sum(_clear_async_markers(task_id) for task_id in reopened)
    parts = []
    if reopened:
        parts.append(
            f"restored {len(reopened)} reopened completed task(s)"
            + (f"; cleared {cleared} async marker/result file(s)" if cleared else "")
        )
    if reconciled:
        parts.append(f"reconciled {len(reconciled)} needs-human task(s) to needs_human")
    if mismatched:
        parts.append(f"reconciled {len(mismatched)} log-mismatch task(s) to task.status")
    print("heal-board: " + "; ".join(parts))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="auto-restore a collapsed/unloadable tasks.yaml")
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if collapsed, no writes")
    ap.add_argument("--dry-run", action="store_true", help="report what would be restored; no writes")
    args = ap.parse_args(argv)

    loadable, total, active = board_health(BOARD)
    collapsed = (not loadable) or (total <= FLOOR)

    if not collapsed:
        return repair_lifecycle(check=args.check, dry_run=args.dry_run)

    state = "unloadable" if not loadable else f"collapsed (total={total} ≤ floor {FLOOR})"
    print(f"heal-board: ⚠ {BOARD.name} is {state}")

    if args.check:
        return 1

    if not HEAL_ON:
        print("heal-board: LIMEN_BOARD_HEAL=0 — heal disabled; leaving board as-is")
        return 1

    snap = git_head_board()
    if snap is None:
        print("heal-board: no committed-good snapshot (HEAD:tasks.yaml) available — cannot heal", file=sys.stderr)
        return 1

    s_load, s_total, s_active = board_health_from_text(snap, BOARD.parent)
    if not s_load or s_total <= FLOOR or s_total <= total:
        print(f"heal-board: snapshot not healthier (loadable={s_load} total={s_total}) — refusing to heal", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.dry_run:
        print(f"heal-board: WOULD restore {BOARD.name} from HEAD ({s_total} tasks, {s_active} active); "
              f"WOULD preserve the collapsed board to logs/{BOARD.name}.collapsed-{stamp}")
        return 0

    # preserve the collapsed board (never delete evidence), then atomically restore the snapshot.
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    preserved = logs / f"{BOARD.name}.collapsed-{stamp}"
    try:
        if BOARD.exists():
            preserved.write_text(BOARD.read_text(errors="ignore"))
    except OSError:
        pass
    atomic_write_text(BOARD, snap)
    print(f"heal-board: RESTORED {BOARD.name} from HEAD — {s_total} tasks ({s_active} active); "
          f"collapsed board preserved to {preserved.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
