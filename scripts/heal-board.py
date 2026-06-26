#!/usr/bin/env python3
"""heal-board.py — the BOARD-INTEGRITY self-heal (autopoietic recovery net).

The collapse-guard in `limen.io.save_limen_file` makes the 2026-06-26 incident — a writer
atomically replacing the live 1449-task queue with one freshly-built task — impossible going
forward. This script is the belt-and-suspenders behind that guard: if the live board is EVER
unloadable or collapsed (a non-atomic external write, disk corruption, a guard-bypassed path,
a future regression), restore it from the last committed-good snapshot (`git show HEAD:tasks.yaml`)
instead of leaving the daemon idling on a dead queue. This is the "fix the handoff so it ain't
broken" self-heal: the institution recovers ITSELF instead of waiting for a human hand-restore.

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
from limen.io import atomic_write_text, load_limen_file  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
HEAL_ON = os.environ.get("LIMEN_BOARD_HEAL", "1") != "0"
ACTIVE = {"open", "dispatched", "in_progress", "needs_human"}

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="auto-restore a collapsed/unloadable tasks.yaml")
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if collapsed, no writes")
    ap.add_argument("--dry-run", action="store_true", help="report what would be restored; no writes")
    args = ap.parse_args(argv)

    loadable, total, active = board_health(BOARD)
    collapsed = (not loadable) or (total <= FLOOR)

    if not collapsed:
        print(f"heal-board: OK — {BOARD.name} healthy (total={total} active={active})")
        return 0

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
