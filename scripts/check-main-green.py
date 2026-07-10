#!/usr/bin/env python3
"""Trunk-green invariant — detect (and optionally heal) a RED main, so it can never sit broken.

The gap this closes (2026-07-10): main's REQUIRED ``pr-gate`` silently went red (non-hermetic tests)
and *nothing detected it*. It blocked every PR until a human noticed and a reactive lane fixed it —
in parallel with a duplicate fix. Beat sensors watch creds / cartridge / lanes / ship-artifacts, but
none watched whether **main's own CI is green**.

Signal. ``pr-gate.yml`` runs on ``pull_request`` only, so it never runs on main. ``ci.yml`` runs on
``push: [main]`` with the SAME pytest suite — so the latest completed ``CI`` run on main is the
trunk-health proxy for pr-gate. This sensor reads it (`gh run list --workflow ci.yml -b main`), and:

- **DETECT (always on):** on a RED verdict it exits non-zero so the beat surfaces ``↑ main trunk RED``
  — closing the silence gap. Verdict is cached (throttled `gh`) so it surfaces every beat cheaply.
- **HEAL (dark until armed, ``LIMEN_MAIN_GREEN_APPLY=1``):** emit ONE idempotent
  ``HEAL-mainred-organvm-limen-<sha>`` task via the daemon's queue-lock (the same safe shared-append
  path self-heal.py uses) — a single canonical task all lanes converge on, closing the duplicate-work
  gap. Observable-before-autonomous: detection ships armed, emission ships dark.

Fail-open: no ``gh`` / offline / parse error → exit 0 (never breaks the beat).

  python3 scripts/check-main-green.py             # detect + surface (+ emit if APPLY=1)
  python3 scripts/check-main-green.py --dry-run    # detect + report only, never emit
  python3 scripts/check-main-green.py --throttle 900
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LOCKD = ROOT / "logs" / ".queue.lock.d"
STAMP = ROOT / "logs" / "main-green.json"
WORKFLOW = os.environ.get("LIMEN_MAIN_GREEN_WORKFLOW", "ci.yml")
REPO = os.environ.get("LIMEN_MAIN_GREEN_REPO", "organvm/limen")
RED = {"failure", "cancelled", "timed_out", "startup_failure"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gh_latest_main_run() -> dict | None:
    """Latest COMPLETED CI run on main (push event). None on any error → caller fails open."""
    try:
        out = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                REPO,
                "--workflow",
                WORKFLOW,
                "--branch",
                "main",
                "--limit",
                "8",
                "--json",
                "databaseId,conclusion,status,headSha,url,event",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return None
        runs = json.loads(out.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    for run in runs:
        if run.get("event") == "push" and run.get("status") == "completed":
            return run
    return None


def _read_stamp() -> dict:
    try:
        return json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_stamp(payload: dict) -> None:
    try:
        STAMP.parent.mkdir(exist_ok=True)
        STAMP.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def verdict(throttle: int) -> dict:
    """Return {conclusion, head_sha, url, source}. Uses cached verdict within the throttle window."""
    cached = _read_stamp()
    if cached.get("checked_at"):
        try:
            age = (_now() - datetime.fromisoformat(cached["checked_at"])).total_seconds()
        except ValueError:
            age = throttle + 1
        if age < throttle and cached.get("conclusion"):
            return {**cached, "source": "cache"}
    run = _gh_latest_main_run()
    if run is None:
        # fail open: keep the last known verdict if any, else "unknown"
        return (
            {**cached, "source": "gh-unavailable"}
            if cached.get("conclusion")
            else {"conclusion": "unknown", "source": "gh-unavailable"}
        )
    payload = {
        "checked_at": _now().isoformat(timespec="seconds"),
        "conclusion": run.get("conclusion") or "unknown",
        "head_sha": (run.get("headSha") or "")[:8],
        "url": run.get("url") or "",
    }
    _write_stamp(payload)
    return {**payload, "source": "gh"}


def _emit_heal_task(head_sha: str, url: str, tasks_path: Path) -> str | None:
    """Emit ONE idempotent HEAL-mainred task under the queue-lock. Returns the id, or None."""
    tid = f"HEAL-mainred-{REPO.replace('/', '-').lower()}-{head_sha or 'head'}"
    for _ in range(15):
        try:
            LOCKD.mkdir()
            break
        except FileExistsError:
            return None  # daemon holds the lock — retry next beat
        except OSError:
            return None
    try:
        lf = load_limen_file(tasks_path)
        if any(t.id == tid for t in lf.tasks):
            return None  # already emitted — idempotent
        stamp = _now().date().isoformat()
        lf.tasks.append(
            Task(
                id=tid,
                title=f"Restore main to green — {REPO} CI is RED at {head_sha}",
                repo=REPO,
                type="code",
                target_agent="any",
                priority="critical",
                budget_cost=1,
                status="open",
                labels=["lifecycle", "ci", "mainred"],
                urls=[url] if url else [],
                context=(
                    f"main's CI ({WORKFLOW}) is RED at {head_sha} ({url}). Reproduce with "
                    "`PYTHONPATH=cli/src pytest web/api/tests cli/tests -q`, fix at root, land a heal PR. "
                    f"Single canonical task (stable id {tid}) so lanes converge instead of duplicating. "
                    f"[auto-emitted {stamp} by check-main-green]"
                ),
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
        )
        save_limen_file(tasks_path, lf)
        return tid
    finally:
        try:
            LOCKD.rmdir()
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="trunk-green invariant sensor")
    ap.add_argument("--dry-run", action="store_true", help="detect + report only, never emit a task")
    ap.add_argument("--throttle", type=int, default=int(os.environ.get("LIMEN_MAIN_GREEN_THROTTLE", "1800")))
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    args = ap.parse_args(argv)

    v = verdict(args.throttle)
    conclusion = v.get("conclusion", "unknown")
    head = v.get("head_sha", "")
    url = v.get("url", "")

    if conclusion == "unknown":
        print(f"check-main-green: SKIP — main CI status unavailable ({v.get('source')}); failing open")
        return 0
    if conclusion not in RED:
        print(f"check-main-green: GREEN — main {WORKFLOW} {conclusion} @ {head} ({v.get('source')})")
        return 0

    # RED
    print(f"check-main-green: RED — main {WORKFLOW} {conclusion} @ {head} ({url})")
    apply_on = os.environ.get("LIMEN_MAIN_GREEN_APPLY", "0").strip() == "1"
    if apply_on and not args.dry_run:
        tid = _emit_heal_task(head, url, Path(args.tasks))
        if tid:
            print(f"  → emitted heal task {tid}")
        else:
            print("  → heal task already open / lock busy (idempotent)")
    else:
        print("  → detection-only (LIMEN_MAIN_GREEN_APPLY!=1); arm it to auto-emit one heal task")
    return 1


if __name__ == "__main__":
    sys.exit(main())
