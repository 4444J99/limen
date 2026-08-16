#!/usr/bin/env python3
"""ships-24h-refresh.py — ground-truth PRs-merged-in-24h, so the ship-milestone notifier fires.

`money-view.py` and `omni-view.py` used to count "ships in the last 24h" by grep-parsing
`logs/merge-drain.log` for `_TS_RE`/`_PR_RE` matches. That log is written ONLY by the batch
`merge-drain.py` daemon's own merges. But this repo's real merge protocol has individual sessions
self-merge their own green PRs directly (`merge-policy.sh` -> `await-pr.sh --merge`), which never
touches that log — so the count structurally missed most of the fleet's real throughput. Measured
2026-08-15: `merge-drain.log` showed `merged=0` on every beat all day while `gh` showed 63 real
merges. `notify-events.py`'s ship-milestone push (10/25/50/100 in 24h) could never fire from real
activity as a result.

This asks GitHub directly instead — one `gh search prs --merged` call across every owner, same
transport `_pr_scan.py`'s open-PR census already uses — and caches the answer to `logs/ships-24h.json`
so `money-view.py`/`omni-view.py` stay pure local-file readers (no network on every view render).

Self-owned wall-clock interval (LIMEN_SHIPS_24H_REFRESH_INTERVAL_MINUTES, default 20): the beat's
own cadence is in BEATS, not minutes, and beat spacing is adaptive — a second, wall-clock-based due
check keeps this from re-querying `gh` faster than the count could plausibly have changed, mirroring
`pr-debt-trend.py`'s `_due_reason` pattern.

Fail-open throughout: any transport/parse failure writes an error-flagged cache (never a stale
"0 ships" silently presented as fresh) and never raises into the beat.

    python3 scripts/ships-24h-refresh.py            # refresh if due
    python3 scripts/ships-24h-refresh.py --dry-run  # report the decision, touch nothing
    python3 scripts/ships-24h-refresh.py --force    # refresh regardless of the wall-clock gate
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pr_scan import enumerate_merged_prs_result  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
CACHE = LOGS / "ships-24h.json"
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
WINDOW_HOURS = 24
RECENT_KEEP = 12


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _cache_age_minutes(now):
    try:
        stamp = json.loads(CACHE.read_text()).get("generated_at")
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            when = when.astimezone()
        return (now - when).total_seconds() / 60.0
    except Exception:
        return None  # fail-open: unreadable/absent cache ⇒ always due


def _atomic_write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ships-24h.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refresh(*, dry_run: bool, force: bool) -> int:
    interval = _int("LIMEN_SHIPS_24H_REFRESH_INTERVAL_MINUTES", 20)
    now = datetime.now(timezone.utc)
    age = _cache_age_minutes(now)
    if not force and age is not None and age < interval:
        print(f"ships-24h-refresh: not due — cache {age:.1f}m old (interval {interval}m)")
        return 0

    since = now - timedelta(hours=WINDOW_HOURS)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    if dry_run:
        print(
            f"ships-24h-refresh: DUE (cache {age}m old, interval {interval}m) — would query gh for owners "
            f"{OWNERS} merged since {since_iso}"
        )
        return 0

    timeout = _int("LIMEN_SHIPS_24H_REFRESH_TIMEOUT", 60)
    result = enumerate_merged_prs_result(
        OWNERS,
        lambda cmd: gh(cmd, timeout=timeout),
        since_iso,
    )

    by_repo = {}
    recent = []
    for repo, num in result.rows:
        by_repo[repo] = by_repo.get(repo, 0) + 1
        recent.append(f"{repo}#{num}")

    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "since": since_iso,
        "window_hours": WINDOW_HOURS,
        "total": len(result.rows),
        "by_repo": by_repo,
        "recent": recent[-RECENT_KEEP:],
        "complete": result.complete,
        "error": None if result.success else result.error,
    }
    _atomic_write(CACHE, payload)
    status = "ok" if result.success else f"FAILED ({result.error})"
    print(f"ships-24h-refresh: {status} — {payload['total']} merged since {since_iso} across {len(OWNERS)} owner(s)")
    return 0 if result.success else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report the due decision, touch nothing")
    ap.add_argument("--force", action="store_true", help="refresh regardless of the wall-clock gate")
    args = ap.parse_args()
    try:
        return refresh(dry_run=args.dry_run, force=args.force)
    except Exception as exc:  # fail-open: this must never break the beat
        print(f"ships-24h-refresh: unexpected error, leaving prior cache in place: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
