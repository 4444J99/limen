#!/usr/bin/env python3
"""PR-debt trend — is the estate's open-PR debt going DOWN?

IF-AMALGAMATION states the ideal: "the fleet amalgamates portals faster than it spawns them; a
predicate measures open-PR plus unmerged-branch debt and the merge daemon drives it monotonically
down." Its registry row carried `probe: null`, and the reason it gave was exact and honest:

    "The ideal is a monotonic TREND, not a level, and a level is the only thing measurable in
     one shot: `gh pr list` returns today's count with nothing to compare it against. A real
     probe needs a committed series, so the debt-trend recorder is this row's next form."

THE SERIES WAS ALREADY COMMITTED. `docs/github-pr-debt-ledger.json` carries `open_pr_count` and
`generated_at`, `scripts/gitvs.py` has been writing it since 2026-07-22, and every write is a
commit. Five observations sat in `git log` for eleven days, unread — the same species as every
other defect in this workstream: a value produced and consumed by nothing. This reads them.

What they say is the point:

    2026-07-22  1059        The ideal's own word is "monotonically DOWN."
    2026-07-23  1111        The measured trend is +105 in three days, ~35/day up.
    2026-07-24  1115        And it stopped being recorded on 07-25, so nothing has
    2026-07-24  1117        even been LOOKING for eight days.
    2026-07-25  1164

STALENESS IS NOT AT-IDEAL, and this is the half a naive trend predicate gets wrong. A debt series
you stopped recording is not a debt trend that improved; it is a debt trend you stopped measuring.
Past LIMEN_PR_DEBT_MAX_AGE_DAYS the predicate fails on the silence itself and says so.

    python3 scripts/pr-debt-trend.py --series   # print every observation git can show
    python3 scripts/pr-debt-trend.py --check    # exit 0 iff the debt is not growing (the probe)

`environment: host` in ideal-forms.yaml, deliberately: a shallow CI checkout truncates git history,
and this must never read "at ideal" because the evidence was clipped away.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_REL = "docs/github-pr-debt-ledger.json"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _git(*args: str, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout


def _count_from(blob: str) -> int | None:
    """The ledger's own field. `expected_open_pr_count` is the reconciliation target, not the debt."""
    try:
        data = json.loads(blob)
    except ValueError:
        return None
    n = data.get("open_pr_count")
    return int(n) if isinstance(n, int) else None


def series() -> list[tuple[str, int, str]]:
    """Every observation git can show, oldest first, as (date, open_pr_count, source).

    Derived, never stored. A recorder that wrote its own series file would be a second copy of a
    number git already versions — and the whole reason this row had no probe was that someone
    thought the series had to be built before it could be read.
    """
    rc, out = _git("log", "--format=%H %ad", "--date=short", "--", LEDGER_REL)
    rows: list[tuple[str, int, str]] = []
    if rc == 0:
        for line in out.splitlines():
            sha, _, date = line.partition(" ")
            if not sha:
                continue
            rc2, blob = _git("show", f"{sha}:{LEDGER_REL}")
            n = _count_from(blob) if rc2 == 0 else None
            if n is not None:
                rows.append((date.strip(), n, sha[:8]))
    rows.reverse()  # git log is newest-first; a series reads forward

    # The working tree may hold an observation newer than any commit — gitvs writes the file
    # before anything commits it. Counting it keeps the freshness check honest about what the
    # producer actually did, rather than about when someone last committed its output.
    live = ROOT / LEDGER_REL
    if live.is_file():
        n = _count_from(live.read_text(encoding="utf-8"))
        if n is not None:
            try:
                stamp = str(json.loads(live.read_text(encoding="utf-8")).get("generated_at") or "")[:10]
            except ValueError:
                stamp = ""
            if stamp and (not rows or stamp > rows[-1][0]):
                rows.append((stamp, n, "worktree"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", action="store_true", help="print every observation git can show")
    ap.add_argument("--check", action="store_true", help="exit 0 iff the debt is not growing")
    args = ap.parse_args()

    rows = series()
    if args.series:
        print(f"PR-debt series — derived from git history of {LEDGER_REL}\n")
        prev = None
        for date, n, src in rows:
            delta = "" if prev is None else f"  {n - prev:+d}"
            print(f"  {date}  open_pr_count={n:<6}{delta:<8} [{src}]")
            prev = n
        print()
        if not rows:
            print("  (no observation is visible — see --check for why that is not a pass)")
        return 0

    if not args.check:
        ap.print_help()
        return 2

    window = _int("LIMEN_PR_DEBT_WINDOW_DAYS", 14)
    max_age = _int("LIMEN_PR_DEBT_MAX_AGE_DAYS", 3)

    if len(rows) < 2:
        # Not "at ideal" and not drift in the predicate — the evidence is absent. Fail, because a
        # trend nobody can see is exactly the state this row was in for eleven days.
        print(f"pr-debt-trend: UNMEASURABLE — {len(rows)} observation(s) in git history of {LEDGER_REL}")
        print("  a trend needs two points; the producer is scripts/gitvs.py reconcile")
        return 1

    newest_date, newest, _ = rows[-1]
    rc, today = _git("log", "-1", "--format=%ad", "--date=short")
    today = today.strip() or newest_date
    age = _days_between(newest_date, today)

    # The window is a slice of the SERIES, not of the calendar: observations are irregular, and
    # comparing against "whatever was recorded 14 days ago" is what makes this a trend and not a
    # pair of numbers.
    in_window = [r for r in rows if _days_between(r[0], newest_date) <= window] or rows[-2:]
    oldest_date, oldest, _ = in_window[0]
    growth = newest - oldest

    print(
        f"pr-debt-trend: debt_growth={growth:+d} over {len(in_window)} observation(s) "
        f"{oldest_date}..{newest_date} (from {oldest} to {newest})"
    )

    if age > max_age:
        print(f"  ✗ STALE — the newest observation is {age}d old (tolerance {max_age}d)")
        print("      silence is not improvement: a debt series nobody records is not a debt trend")
        print("      the producer is `python3 scripts/gitvs.py reconcile` (sensor: github-estate-reconcile)")
        return 1
    if growth > 0:
        print(f"  ✗ the debt GREW by {growth} — the ideal is monotonically down")
        return 1
    print(f"  ✓ the debt is not growing over the last {window} day(s) of observations")
    return 0


def _days_between(a: str, b: str) -> int:
    import datetime

    try:
        return abs((datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days)
    except ValueError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
