#!/usr/bin/env python3
"""jules-flywheel — THE one predicate: exit 0 ⟺ the compound loop turns.

The jules-flywheel program (docs/plans/2026-08-06-jules-flywheel.md, issue #1874) exists
so that dispatched work COMPOUNDS: quota consumed, work landing, debt falling. Each half
has its own gauges (jules-quota, lane-throughput, the PR-debt ledger); this sensor is the
single acceptance predicate over all three, and its exit 1 names the failing clause AND
the effector that owns the fix — never a bare red.

  1  QUOTA    dispatched_today >= 0.8 x daily target, judged only after
              LIMEN_JULES_QUOTA_ALARM_HOUR (18 UTC — the day must be old enough to judge).
              Owner when red: jules-supply / work-loan-backfill (no packets) or
              dispatch-beat + autonomy-policy (valve shut).
  2  LANDING  landed/dispatched over the throughput window >= LIMEN_FLYWHEEL_LAND_FLOOR
              (default 0.30) — SKIPPED while window dispatches < bootstrap_min (the same
              cold-start escape the throughput governor allows; the flywheel must not
              alarm on the ramp it deliberately permits).
              Owner when red: jules-land / owner-route-drain / merge-drain.
  3  DEBT     jules-authored open-PR count non-increasing vs the last snapshot
              (logs/jules-pr-debt-snapshot.json). Fail-open with a note when gh is
              unavailable (probe_unavailable, like jules-quota).
              Owner when red: owner-route-drain.

Read-only over the board; the only write is its own debt snapshot.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.capacity import derived_daily_floor, lane_throughput_window  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
SNAPSHOT = Path(os.environ.get("LIMEN_JULES_PR_DEBT_SNAPSHOT", str(ROOT / "logs" / "jules-pr-debt-snapshot.json")))
JULES_AUTHOR = os.environ.get("LIMEN_JULES_PR_AUTHOR", "app/google-labs-jules")
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]


def _now() -> datetime:
    """Seam for tests; the predicate itself always judges live UTC."""
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def dispatched_today(board: object, today: date) -> int:
    """Jules dispatch receipts stamped today (UTC) — the jules-quota used_today convention."""
    used = 0
    for task in getattr(board, "tasks", None) or []:
        for entry in task.dispatch_log or []:
            if str(getattr(entry, "agent", "") or "").lower() != "jules":
                continue
            if str(getattr(entry, "status", "") or "").lower() != "dispatched":
                continue
            stamp = getattr(entry, "timestamp", None)
            if isinstance(stamp, datetime) and stamp.date() == today:
                used += 1
    return used


def open_jules_pr_count() -> int | None:
    """Live count of jules-authored open PRs, or None when gh cannot answer."""
    cmd = [
        "gh",
        "search",
        "prs",
        "--state",
        "open",
        "--author",
        JULES_AUTHOR,
        *sum([["--owner", o] for o in OWNERS], []),
        "--limit",
        "1000",
        "--json",
        "number",
        "--jq",
        "length",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def main() -> int:
    board = load_limen_file(TASKS)
    now = _now()
    target = derived_daily_floor("jules", board)
    alarm_hour = _env_int("LIMEN_JULES_QUOTA_ALARM_HOUR", 18)
    land_floor = _env_float("LIMEN_FLYWHEEL_LAND_FLOOR", 0.30)
    bootstrap_min = _env_int("LIMEN_THROUGHPUT_BOOTSTRAP_MIN", 20)

    failures: list[str] = []
    notes: list[str] = []

    # 1 QUOTA
    used = dispatched_today(board, now.date())
    quota_floor = int(round(0.8 * target))
    if now.hour >= alarm_hour and used < quota_floor:
        failures.append(
            f"quota: dispatched_today={used} < {quota_floor} (0.8 x target {target}) after {alarm_hour}:00Z "
            "— owners: jules-supply / work-loan-backfill (packets) or dispatch-beat + autonomy-policy (valve)"
        )
    else:
        notes.append(f"quota used={used}/{target}")

    # 2 LANDING
    dispatched_w, landed_w = lane_throughput_window(board, "jules", now=now)
    if dispatched_w < bootstrap_min:
        notes.append(f"landing skipped (window dispatches {dispatched_w} < bootstrap_min {bootstrap_min})")
    else:
        rate = landed_w / dispatched_w
        if rate < land_floor:
            failures.append(
                f"landing: rate {rate:.0%} ({landed_w}/{dispatched_w}) < floor {land_floor:.0%} "
                "— owners: jules-land / owner-route-drain / merge-drain"
            )
        else:
            notes.append(f"landing rate={rate:.0%}")

    # 3 DEBT
    count = open_jules_pr_count()
    if count is None:
        notes.append("debt probe_unavailable(gh)")
    else:
        previous: int | None = None
        try:
            previous = int(json.loads(SNAPSHOT.read_text()).get("open_jules_prs"))
        except (OSError, ValueError, TypeError):
            previous = None
        if previous is not None and count > previous:
            failures.append(
                f"debt: open jules PRs rose {previous} -> {count} — owner: owner-route-drain "
                "(arm LIMEN_OWNER_ROUTE_DRAIN_APPLY after reviewing its census)"
            )
        else:
            notes.append(f"debt open={count}" + (f" (was {previous})" if previous is not None else " (first snapshot)"))
        try:
            SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT.write_text(
                json.dumps(
                    {"open_jules_prs": count, "observed_at": now.isoformat(timespec="seconds")},
                    indent=2,
                )
                + "\n"
            )
        except OSError:
            pass

    if failures:
        for failure in failures:
            print(f"  jules-flywheel: FAIL {failure}")
        return 1
    print("  jules-flywheel: OK — " + "; ".join(notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
