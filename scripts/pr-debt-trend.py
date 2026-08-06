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
    runs every cadence; the census runs on a wall-clock interval, and it is due only when BOTH
    clocks agree — see `_due_reason`, and the duplicate that proved one clock is not enough.
  · it does NOT ship an unchanged census — a PR-debt recorder that adds a PR per beat refutes
    itself. Change is judged by `_stable_digest`, NOT by the ledger's own `content_sha256`.

    THE FIRST CUT SHIPPED NOISE ANYWAY, and the reason is worth keeping. This file used to say
    change was judged by `content_sha256`, "which the ledger computes with `generated_at` excluded,
    precisely so two censuses of an unchanged estate compare equal." That is true of the top-level
    field and false of the document: gitvs.py:827 excludes only top-level `generated_at` and the
    hash itself, while every one of the ~1,300 records inside `pull_requests` carries its own
    freshly-stamped `disposition_observed_at` and a recomputed `age_hours`. Both are inside the
    hash, so the hash moves on EVERY run, unconditionally.

    The property was asserted from the field's name and its exclusion list and never tested by
    running the census twice. Verified now, against the real 1,293-record ledger: advance only
    the clock fields and `content_sha256` moves while `_stable_digest` holds, and a single PR
    leaving the estate still moves the digest.

    ATTRIBUTION, CORRECTED. An earlier version of this paragraph called PR #1859 the receipt for
    this defect — "a 2,461-line diff recording 1293 -> 1293". The count is right and the reading
    was wrong: #1858 was OPENED at 03:27:43Z, between the 03:17 and 03:31 censuses, so the PR set
    genuinely moved and 1293 held only because something merged in the same window. #1859 carried
    real information. What produced it is the CLOCK below, on its own — two censuses fourteen
    minutes apart under a twenty-hour interval. The change-basis defect is real, independent, and
    would ship on every run forever; it just is not what #1859 demonstrates. Saying otherwise was
    the same move that caused the bug: a confident claim about data nobody had diffed.
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
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_REL = "docs/github-pr-debt-ledger.json"
# The census's private receipt. Gitignored by design (`logs/.gitignore`), which is what makes it a
# good clock for "did *this checkout* run the sweep recently": nothing ever restores or reverts it,
# so a run that produced no change still leaves a mark, and the expensive 169-page sweep is not
# repeated every cadence just because the estate held still.
#
# It is a LOCAL clock, and that is the half the first cut missed. Being gitignored, it is per
# checkout: the beat runs from the live checkout and a session runs from a worktree, and neither
# can see the other's mtime. So a manual --record at 03:17 left no mark the beat could read, the
# beat ran its own census at 03:31, and the "20h interval" throttled nothing across the boundary.
# The shared half of the clock is _last_recorded_utc(), read from git, which every checkout shares.
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


def _generated_at(blob: str) -> str | None:
    """The ledger's own UTC stamp — the only safe basis for ordering two ledgers in time.

    git's `--date=short` is the author's LOCAL date. Comparing it against this one is comparing
    two different clocks, and the series did exactly that until a run of `--series` showed the
    same 1,293-PR ledger twice: once as its commit, once as `[worktree]` a calendar day later.
    """
    try:
        data = json.loads(blob)
    except ValueError:
        return None
    stamp = data.get("generated_at")
    return stamp if isinstance(stamp, str) and stamp else None


def series() -> list[tuple[str, int, str]]:
    """Every observation git can show, oldest first, as (date, open_pr_count, source).

    Derived, never stored. A recorder that wrote its own series file would be a second copy of a
    number git already versions — and the whole reason this row had no probe was that someone
    thought the series had to be built before it could be read.
    """
    rc, out = _git("log", "--format=%H %ad", "--date=short", "--", LEDGER_REL)
    rows: list[tuple[str, int, str]] = []
    newest_blob = ""
    if rc == 0:
        for line in out.splitlines():
            sha, _, date = line.partition(" ")
            if not sha:
                continue
            rc2, blob = _git("show", f"{sha}:{LEDGER_REL}")
            n = _count_from(blob) if rc2 == 0 else None
            if n is not None:
                if not newest_blob:
                    newest_blob = blob  # git log is newest-first, so the first hit is the newest
                rows.append((date.strip(), n, sha[:8]))
    rows.reverse()  # git log is newest-first; a series reads forward

    # The working tree may hold an observation newer than any commit — gitvs writes the file
    # before anything commits it. Counting it keeps the freshness check honest about what the
    # producer actually did, rather than about when someone last committed its output.
    #
    # It counts only when it is a DIFFERENT OBSERVATION than the newest committed one, and both
    # halves of that test were wrong. Identity was "is its date later?", which re-rendered an
    # already-committed observation whenever the clock alone had moved; and the comparison put the
    # ledger's UTC `generated_at` against git's `--date=short`, the author's LOCAL date, so any
    # census run after ~20:00 local looked a calendar day newer than the commit holding its own
    # identical bytes. Verification caught it as a phantom `+0` row attributed to `[worktree]`
    # sitting under the commit it was a copy of. Identity is now the stable digest — the same
    # basis `record()` ships on — and ordering compares UTC to UTC.
    live = ROOT / LEDGER_REL
    if live.is_file():
        blob = live.read_text(encoding="utf-8")
        n = _count_from(blob)
        stamp = _generated_at(blob)
        if n is not None and stamp and _stable_digest(blob) != _stable_digest(newest_blob):
            newest_stamp = _generated_at(newest_blob)
            if newest_stamp is None or stamp > newest_stamp:
                rows.append((stamp[:10], n, "worktree"))
    return rows


# Every key whose value moves with the wall clock rather than with the estate. Stripped at any
# depth before hashing. `disposition_observed_at` and `age_hours` live on each of ~1,300 per-PR
# records and are re-derived from `now` on every census, which is why the ledger's own
# `content_sha256` — computed over them — cannot answer "did anything but the clock move?".
VOLATILE_KEYS = frozenset({"generated_at", "content_sha256", "disposition_observed_at", "age_hours"})


def _strip_volatile(node: object) -> object:
    if isinstance(node, dict):
        return {k: _strip_volatile(v) for k, v in node.items() if k not in VOLATILE_KEYS}
    if isinstance(node, list):
        return [_strip_volatile(v) for v in node]
    return node


def _stable_digest(blob: str) -> str | None:
    """Identity of an observation: the whole ledger minus every clock-driven field.

    This is what `content_sha256` is usually assumed to be and is not (see the module docstring).
    Hashing the stripped document — rather than a hand-picked summary — keeps composition inside
    the identity: if the count holds at 1293 but a different set of PRs is open, or the untyped
    count moves, that IS an observation and it ships. Only time passing is not.
    """
    try:
        data = json.loads(blob)
    except ValueError:
        return None
    canonical = json.dumps(_strip_volatile(data), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _last_census_utc() -> _dt.datetime | None:
    """When THIS CHECKOUT last ran the census, from the gitignored receipt's mtime. None ⇒ never."""
    facts = ROOT / FACTS_REL
    if not facts.is_file():
        return None
    try:
        return _dt.datetime.fromtimestamp(facts.stat().st_mtime, tz=_dt.timezone.utc)
    except OSError:
        return None


def _last_recorded_utc() -> _dt.datetime | None:
    """When an observation was last RECORDED, read from the committed ledger. None ⇒ unknown.

    The shared half of the clock. Read from git rather than from the working tree precisely so a
    local revert of an unchanged census cannot reset it, and so every checkout — beat, worktree,
    session — answers "has anyone recorded recently?" identically. Falls back through the local
    default branch, then HEAD, for a checkout with no `origin` (the test repos, and a clone that
    has not fetched).
    """
    for ref in ("origin/main", "main", "HEAD"):
        rc, blob = _git("show", f"{ref}:{LEDGER_REL}")
        if rc != 0 or not blob.strip():
            continue
        try:
            stamp = json.loads(blob).get("generated_at")
        except ValueError:
            continue
        if not isinstance(stamp, str) or not stamp:
            continue
        try:
            return _dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(_dt.timezone.utc)
        except ValueError:
            continue
    return None


def _due_reason(now: _dt.datetime, interval: int) -> str | None:
    """None ⇒ due. A string ⇒ why not, ready to print.

    Due requires BOTH clocks to be stale: this checkout has not swept recently AND nobody has
    recorded recently. Either alone is insufficient — the local receipt alone let two checkouts
    census fourteen minutes apart (#1859), and the committed observation alone would re-run the
    169-page sweep every cadence for as long as the estate held still.
    """
    for label, last in (
        ("this checkout swept", _last_census_utc()),
        ("an observation was recorded", _last_recorded_utc()),
    ):
        if last is None:
            continue
        age_h = (now - last).total_seconds() / 3600.0
        if age_h < interval:
            return f"not due — {label} {age_h:.1f}h ago (interval {interval}h)"
    return None


def record(*, dry_run: bool) -> int:
    """Run the census when it is due and ship the observation only if the estate actually moved."""
    interval = _int("LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS", 20)
    now = _dt.datetime.now(_dt.timezone.utc)
    blocked = _due_reason(now, interval)
    if blocked is not None:
        print(f"pr-debt-record: {blocked}")
        return 0

    ledger = ROOT / LEDGER_REL
    before = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    before_digest = _stable_digest(before)

    if dry_run:
        print(f"pr-debt-record: DUE (interval {interval}h, both clocks stale) — would run:")
        print(f"    {' '.join(PRODUCER_ARGV)}")
        print(f"  then ship {LEDGER_REL} via {SHIP} only if the stable digest moves from {before_digest}")
        return 0

    proc = subprocess.run(PRODUCER_ARGV, cwd=str(ROOT), capture_output=True, text=True, check=False)
    census_out = (proc.stdout or "").strip().splitlines()
    print(f"pr-debt-record: census -> {census_out[-1] if census_out else f'exit {proc.returncode}'}")

    after = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    after_digest = _stable_digest(after)
    if after_digest is None:
        # Restore for the SAME reason the no-change branch below does, and more urgently: a census
        # that died mid-write leaves unparseable JSON in a TRACKED file, and leaving it there hands
        # sync-release.sh and capture.sh a broken ledger to sweep into an unrelated branch. The
        # first cut restored only on the happy path, so the one case where the file is genuinely
        # invalid was the one case left dirty — found by running the failure, not by reading it.
        _git("checkout", "--", LEDGER_REL)
        print("  \u2717 the census wrote no readable ledger — nothing to record, ledger restored")
        print((proc.stderr or "").strip()[:500])
        return 1

    if after_digest == before_digest:
        # The estate held still and only the clock moved — the common case, and the one the first
        # cut got wrong. Restore the tracked file so the live checkout does not carry a
        # permanently-dirty ledger whose only difference is a timestamp; that dirt is what
        # sync-release.sh and capture.sh would otherwise sweep into an unrelated branch.
        _git("checkout", "--", LEDGER_REL)
        print(f"  \u00b7 no change (stable digest {after_digest[:12]}) — nothing shipped, ledger restored")
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
        print(f"  \u2713 observation recorded ({before_digest and before_digest[:12]} -> {after_digest[:12]})")
        return 0
    print(f"  \u2717 ship-docs refused the observation: {(ship.stderr or '').strip()[:300]}")
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
