#!/usr/bin/env python3
"""orphan-watchers.py — no session-spawned PR poll shell outlives its session.

The 2026-07-15 endless-watcher incident: sessions hand-rolled background poll loops
(``for i in $(seq 1 40); do gh pr ...; sleep 45; done`` inside a Claude shell-snapshot zsh)
to babysit merge gates — bespoke, silent on FAIL, and, the defect this organ closes,
invisible once the parent session died: nothing audited or reaped them.

One detection core, three consumers:

  --check                 loud line per ORPHAN watcher (parent session gone, age at/above the
                          floor); journals to logs/session-lifecycle.jsonl; exit 1 if any found.
  --check --reap          the armed effector (the sensor arms it via LIMEN_ORPHAN_WATCHER_REAP=1):
                          TERM -> grace -> KILL, orphans only, every kill journaled.
  --session-end --sid S   SessionEnd audit: loud stderr line per SURVIVING watcher shell,
                          estate-wide, no age floor (surfacing, not judging); always exit 0 —
                          a SessionEnd hook must never block session end.

A WATCHER is a Claude-launched shell (``.claude/shell-snapshots/`` in its command) that both
sleeps (``sleep N``) and polls a PR gate (``gh pr `` or ``merge-policy.sh``) — plus any live
``scripts/await-pr.sh`` run (the sanctioned waiter is still a watcher; an orphaned one past its
deadline is equally reapable). An ORPHAN is a watcher whose parent is gone (or is no longer a
claude process) AND whose age >= LIMEN_ORPHAN_WATCHER_MIN_AGE (default 1800 s — deliberately
above await-pr's 1200 s deadline, so a healthy sanctioned wait can never be reaped).

Test seam: --ps-fixture FILE replays a ``ps -axo pid=,ppid=,etime=,command=`` table.
Sanctioned alternatives the escalation points at: scripts/await-pr.sh (bounded, loud) or the
beat's merge rung (scripts/merge-drain.py via scripts/drain.sh).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
JOURNAL = ROOT / "logs" / "session-lifecycle.jsonl"

_SLEEP_RE = re.compile(r"\bsleep\s+\d+")
_POLL_MARKS = ("gh pr ", "merge-policy.sh")


def parse_etime(etime: str) -> int:
    """ps etime ([[dd-]hh:]mm:ss) -> seconds; unparseable -> 0 (fails toward NOT reaping)."""
    days = 0
    if "-" in etime:
        day_part, etime = etime.split("-", 1)
        try:
            days = int(day_part)
        except ValueError:
            return 0
    fields = etime.split(":")
    try:
        parts = [int(f) for f in fields]
    except ValueError:
        return 0
    if len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    elif len(parts) == 3:
        h, m, s = parts
    else:
        return 0
    return days * 86400 + h * 3600 + m * 60 + s


def parse_ps_table(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid_s, ppid_s, etime, command = parts
        try:
            rows.append({"pid": int(pid_s), "ppid": int(ppid_s), "etime": etime, "command": command})
        except ValueError:
            continue
    return rows


def ps_rows(fixture: str | None) -> list[dict]:
    if fixture:
        return parse_ps_table(Path(fixture).read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,etime=,command="], capture_output=True, text=True, timeout=30, check=False
    )
    return parse_ps_table(proc.stdout) if proc.returncode == 0 else []


def is_watcher(command: str) -> bool:
    if "orphan-watchers.py" in command:
        return False  # never classify this organ (or a wrapper running it) as its own quarry
    if "scripts/await-pr.sh" in command and ".lock" not in command:
        return True
    return (
        ".claude/shell-snapshots/" in command
        and bool(_SLEEP_RE.search(command))
        and any(mark in command for mark in _POLL_MARKS)
    )


def classify(rows: list[dict], min_age: int, self_pid: int = 0) -> tuple[list[dict], list[dict]]:
    """Return (watchers, orphans). Orphan := watcher whose parent is gone or not a claude
    process, and whose age >= min_age. Fails toward NOT-orphan on any ambiguity."""
    by_pid = {r["pid"]: r for r in rows}
    watchers = [r for r in rows if r["pid"] != self_pid and is_watcher(r["command"])]
    orphans = []
    for w in watchers:
        parent = by_pid.get(w["ppid"])
        parent_is_session = parent is not None and "claude" in parent["command"].lower()
        age = parse_etime(w["etime"])
        if not parent_is_session and age >= min_age:
            orphans.append(dict(w, age_s=age))
    return watchers, orphans


def _journal(record: dict) -> None:
    try:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass  # journaling is evidence, never a blocker


def _send(pid: int, sig: int) -> bool:
    """Signal a watcher: its whole process group when it leads one, else the pid alone —
    never a group the watcher merely belongs to (that could be our own caller's)."""
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, sig)
        else:
            os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def reap(orphans: list[dict]) -> int:
    reaped = 0
    for o in orphans:
        pid = o["pid"]
        _send(pid, signal.SIGTERM)
        deadline = time.time() + 2.0
        while time.time() < deadline and _alive(pid):
            time.sleep(0.1)
        if _alive(pid):
            _send(pid, signal.SIGKILL)
        reaped += 1
        _journal(
            {
                "ts": int(time.time()),
                "event": "orphan-watcher-reaped",
                "pid": pid,
                "age_s": o.get("age_s", 0),
                "command": o["command"][:160],
            }
        )
        print(f"orphan-watchers: REAPED pid {pid} (age {o.get('age_s', 0)}s) — {o['command'][:120]}")
    return reaped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="detect orphan watchers; exit 1 if any")
    ap.add_argument("--reap", action="store_true", help="with --check: TERM->KILL the orphans (armed valve)")
    ap.add_argument("--session-end", action="store_true", help="SessionEnd audit of surviving watchers; exit 0")
    ap.add_argument("--sid", default="unknown", help="session id for the --session-end journal record")
    ap.add_argument("--ps-fixture", default=None, help="test seam: read the ps table from a file")
    args = ap.parse_args(argv)
    if args.reap and not args.check:
        ap.error("--reap requires --check")
    if not (args.check or args.session_end):
        ap.error("one of --check or --session-end is required")

    min_age = int(os.environ.get("LIMEN_ORPHAN_WATCHER_MIN_AGE", "1800"))
    rows = ps_rows(args.ps_fixture)
    watchers, orphans = classify(rows, min_age, self_pid=os.getpid())

    if args.session_end:
        if watchers:
            print(
                f"⚠ orphan-watchers: {len(watchers)} PR watcher shell(s) still running at session end "
                f"— use scripts/await-pr.sh or hand off to the merge rung (scripts/drain.sh):",
                file=sys.stderr,
            )
            for w in watchers:
                print(f"    pid {w['pid']} (up {w['etime']}) {w['command'][:120]}", file=sys.stderr)
            _journal(
                {
                    "ts": int(time.time()),
                    "sid": args.sid,
                    "event": "session-end-watcher-audit",
                    "watchers": [
                        {"pid": w["pid"], "etime": w["etime"], "command": w["command"][:160]} for w in watchers
                    ],
                }
            )
        return 0

    if not orphans:
        print(f"orphan-watchers: OK — {len(watchers)} watcher(s), 0 orphaned")
        return 0
    print(f"orphan-watchers: {len(orphans)} ORPHAN PR watcher shell(s) — a session died and left its poll loop:")
    for o in orphans:
        print(f"    pid {o['pid']} (age {o['age_s']}s, parent {o['ppid']} gone) {o['command'][:120]}")
    _journal(
        {
            "ts": int(time.time()),
            "event": "orphan-watchers",
            "orphans": [{"pid": o["pid"], "age_s": o["age_s"], "command": o["command"][:160]} for o in orphans],
        }
    )
    if args.reap:
        reap(orphans)
    return 1


if __name__ == "__main__":
    sys.exit(main())
