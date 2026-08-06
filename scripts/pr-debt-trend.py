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
    python3 scripts/pr-debt-trend.py --record   # run the census when due, ship it on change

THE RECORDER (--record). The five observations above were not recorded by anything: every one is a
side effect of an unrelated feature PR that happened to regenerate the ledger (#1337, #1503, #1508,
#1495, #1541). There was never a producer on a cadence, which is why the series stopped the day that
work stopped — `--check` was a reader with nothing writing to it. `--record` is the writer, wired as
the `github-pr-debt` sensor in institutio/governance/sensors.yaml.

Three things it refuses to do, each because the naive version is worse than nothing:
  · it does NOT run every beat — the beat is adaptive (120s…1800s), so a `cadence: N` is 16 minutes
    on the busy end, and a full paginated estate census does not belong there. The cheap due-check
    runs every cadence; the census runs on a wall-clock interval it owns itself.
  · it does NOT ship an unchanged census — a PR-debt recorder that adds a PR per beat refutes
    itself. Change is judged by `content_sha256`, which the ledger computes with `generated_at`
    excluded; a byte compare would differ on every single run and ship forever.
  · it does NOT commit to main — the observation goes through scripts/ship-docs.sh like every other
    docs-class write (charter § No side doors). capture.sh cannot serve here: it snapshots a live
    default-branch checkout to a side ref and never commits it, so the observation would land
    somewhere `git log -- <ledger>` on main never looks.

`environment: host` in ideal-forms.yaml, deliberately: a shallow CI checkout truncates git history,
and this must never read "at ideal" because the evidence was clipped away.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_REL = "docs/github-pr-debt-ledger.json"
# The census's private receipt. Gitignored by design (`logs/.gitignore`), which is exactly what
# makes it the right clock for "when did the census last RUN": unlike the tracked ledger, nothing
# ever restores or reverts it, so a run that produced no change still leaves a mark. Using the
# ledger's own timestamp instead would reset the clock whenever an unchanged census is reverted,
# and the recorder would re-run the expensive estate sweep on every cadence forever.
FACTS_REL = "logs/gitvs-pr-debt-facts.json"

# The command that actually writes LEDGER_REL, verified by running it — not by reading a sensor
# name. The first version of this file said `gitvs.py reconcile`, because that is the beat-wired
# GitHub sensor and it LOOKED like the producer. It is not: `reconcile` is a dry effector report
# that returns in 0.1s and never touches the ledger. Sending a reader there would have cost them
# the same afternoon it cost to find out, which is the whole failure mode this script measures.
PRODUCER = "python3 scripts/gitvs.py pr-debt --check --json"
PRODUCER_OWNER = "run by the `github-pr-debt` sensor (institutio/governance/sensors.yaml) via --record"
# What --record actually invokes. `--write-ledger` is the flag that makes the census durable; the
# reader above deliberately names the `--json` form because that is the shape a human runs by hand.
PRODUCER_ARGV = ["python3", "scripts/gitvs.py", "pr-debt", "--check", "--write-ledger"]
SHIP = "scripts/ship-docs.sh"


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


def _content_sha(blob: str) -> str | None:
    """The ledger's own `content_sha256` — the census identity with `generated_at` excluded.

    gitvs computes it over every field except `generated_at` and the hash itself, precisely so two
    censuses of an unchanged estate compare equal. Change detection MUST use it: the raw bytes carry
    a fresh timestamp on every run, so a byte compare reports "changed" every time and the recorder
    would open a pull request per beat — against the very debt it exists to measure.
    """
    try:
        data = json.loads(blob)
    except ValueError:
        return None
    sha = data.get("content_sha256")
    return sha if isinstance(sha, str) and sha else None


def _last_census_utc() -> _dt.datetime | None:
    """When the census last RAN, from the gitignored receipt's mtime. None ⇒ never."""
    facts = ROOT / FACTS_REL
    if not facts.is_file():
        return None
    try:
        return _dt.datetime.fromtimestamp(facts.stat().st_mtime, tz=_dt.timezone.utc)
    except OSError:
        return None


def record(*, dry_run: bool) -> int:
    """Run the census when it is due and ship the observation only if the estate actually moved."""
    interval = _int("LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS", 20)
    now = _dt.datetime.now(_dt.timezone.utc)
    last = _last_census_utc()
    if last is not None:
        age_h = (now - last).total_seconds() / 3600.0
        if age_h < interval:
            print(f"pr-debt-record: not due — last census {age_h:.1f}h ago (interval {interval}h)")
            return 0

    ledger = ROOT / LEDGER_REL
    before = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    before_sha = _content_sha(before)

    if dry_run:
        when = "never" if last is None else f"{(now - last).total_seconds() / 3600.0:.1f}h ago"
        print(f"pr-debt-record: DUE (last census {when}, interval {interval}h) — would run:")
        print(f"    {' '.join(PRODUCER_ARGV)}")
        print(f"  then ship {LEDGER_REL} via {SHIP} only if content_sha256 changes from {before_sha}")
        return 0

    proc = subprocess.run(PRODUCER_ARGV, cwd=str(ROOT), capture_output=True, text=True, check=False)
    census_out = (proc.stdout or "").strip().splitlines()
    print(f"pr-debt-record: census -> {census_out[-1] if census_out else f'exit {proc.returncode}'}")

    after = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    after_sha = _content_sha(after)
    if after_sha is None:
        print("  ✗ the census wrote no readable ledger — nothing to record")
        print((proc.stderr or "").strip()[:500])
        return 1

    if after_sha == before_sha:
        # Unchanged estate. Restore the tracked file so the live checkout does not carry a
        # permanently-dirty ledger whose only difference is a timestamp — that dirt is what
        # sync-release.sh and capture.sh would otherwise sweep into an unrelated branch.
        _git("checkout", "--", LEDGER_REL)
        print(f"  · no change (content_sha256 {after_sha[:12]}) — nothing shipped, ledger restored")
        return 0

    msg = f"docs(gitvs): record open-PR debt observation ({_count_from(after)} open)"
    ship = subprocess.run(
        ["bash", str(ROOT / SHIP), "pr-debt-observation", msg, LEDGER_REL],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tail = (ship.stdout or "").strip().splitlines()
    print(f"  ship-docs exit {ship.returncode}: {tail[-1] if tail else '(no output)'}")
    # 0 = merged, 2 = PR open awaiting merge-policy. Both mean the observation is preserved on
    # origin, which is what the series needs; only a refusal (1) is a recording failure.
    if ship.returncode in (0, 2):
        print(f"  ✓ observation recorded ({before_sha and before_sha[:12]} -> {after_sha[:12]})")
        return 0
    print(f"  ✗ ship-docs refused the observation: {(ship.stderr or '').strip()[:300]}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", action="store_true", help="print every observation git can show")
    ap.add_argument("--check", action="store_true", help="exit 0 iff the debt is not growing")
    ap.add_argument("--record", action="store_true", help="run the census when due; ship it on change")
    ap.add_argument("--dry-run", action="store_true", help="with --record: report the decision, touch nothing")
    args = ap.parse_args()

    if args.record:
        return record(dry_run=args.dry_run)

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
        print(f"  a trend needs two points; the producer is `{PRODUCER}`")
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
        print(f"      the producer is `{PRODUCER}` — {PRODUCER_OWNER}")
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
