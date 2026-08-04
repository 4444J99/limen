#!/usr/bin/env python3
"""derive-epochs — the DERIVED half of the biography surface, from hard signals only.

Writes `~/Workspace/_life-private/epochs/index.yaml`: an ordered series of epoch
boundaries measured from metadata. Boundaries are FACTS — a channel carrying tens of
thousands of messages over thirteen months and a few dozen over the next fourteen has a
boundary in it whether or not anyone knows what it meant.

WHAT THIS SCRIPT MAY READ (institutio/governance/biography.yaml -> epoch_signals):
  corpus-thread-dates   per-conversation created_at across the declared session corpora
  repo-activity         git commit months across the live checkout

WHAT IT MAY NEVER DO — and this is the whole contract:
  * read conversation CONTENT. Counting threads per month is not reading them. A boundary
    drawn from what the conversations were ABOUT is the defect the biography registry
    exists to prevent.
  * write a `meaning`. Every epoch is emitted with `meaning: unknown`. What a period WAS
    is not derivable from arithmetic, and an agent that fills it in has fabricated a life
    rather than measured one. `unknown` is a correct answer; a guess is not.
  * overwrite operator-authored meaning. A re-run preserves every meaning already present
    (operator provenance outranks derived), so this is idempotent and safe to re-run.

Usage:
  scripts/derive-epochs.py            # dry-run: print the derived series
  scripts/derive-epochs.py --write    # write the store
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import corpus_resolve  # noqa: E402 — sibling module, path set above

STORE_BASE = Path(os.environ.get("LIMEN_WORKSPACE", str(Path.home() / "Workspace")))
OUT = STORE_BASE / "_life-private" / "epochs" / "index.yaml"

# A run of this many consecutive months at or below QUIET_MAX ends an epoch.
GAP_MONTHS = 3
QUIET_MAX = 2
# A month-over-month swing of this factor against the running mean also ends one.
SURGE_FACTOR = 4.0
# ...but only once an epoch has real extent. Without this, a signal growing exponentially
# (the estate's own commit volume: 17 -> 698 -> 2,858/month) surges EVERY month and
# shatters into one-month epochs, which is noise wearing a boundary's clothes.
MIN_EPOCH_MONTHS = 3
MEANING_PLACEHOLDER = "unknown"


def _iso_month(value) -> str | None:
    """YYYY-MM from an ISO string or a POSIX timestamp; None when unparseable."""
    if isinstance(value, (int, float)) and value > 0:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(value, _dt.timezone.utc).strftime("%Y-%m")
    if isinstance(value, str) and len(value) >= 7 and value[4] == "-":
        return value[:7]
    return None


def _thread_months(corpus_dir: Path) -> Counter:
    """Month -> thread count for one corpus, from metadata only.

    Prefers `conversation-summaries.json` over `conversations.json`: same record count,
    no message bodies, a fraction of the memory. This host has logged jetsam kills, so
    loading a 44 MB body-bearing file to read a date field would be careless.
    """
    source = corpus_dir / "source"
    months: Counter = Counter()
    for name in ("conversation-summaries.json", "conversations.json"):
        path = source / name
        if not path.is_file():
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rows, dict):
            rows = list(rows.values())
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Claude: created_at (ISO). ChatGPT: create_time (POSIX float).
            month = _iso_month(row.get("created_at")) or _iso_month(row.get("create_time"))
            if month:
                months[month] += 1
        if months:
            return months
    return months


def _repo_months() -> Counter:
    """Month -> commit count across the live checkout."""
    result = subprocess.run(
        ["git", "log", "--format=%ad", "--date=format:%Y-%m"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        return Counter()
    return Counter(line.strip() for line in result.stdout.splitlines() if line.strip())


def _month_range(months: Counter) -> list[str]:
    """Every month from first to last observed, including the empty ones."""
    if not months:
        return []
    keys = sorted(months)
    start_y, start_m = (int(x) for x in keys[0].split("-"))
    end_y, end_m = (int(x) for x in keys[-1].split("-"))
    out, y, m = [], start_y, start_m
    while (y, m) <= (end_y, end_m):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _segment(months: Counter, signal: str) -> list[dict]:
    """Split the observed span into epochs at silences and surges."""
    span = _month_range(months)
    if not span:
        return []
    epochs: list[dict] = []
    current: list[str] = []
    quiet_run = 0
    running: list[int] = []

    def close(reason: str) -> None:
        if not current:
            return
        counts = [months.get(mm, 0) for mm in current]
        epochs.append(
            {
                "id": f"{current[0]}--{current[-1]}",
                "start": current[0],
                "end": current[-1],
                "signal": signal,
                "boundary_reason": reason,
                "evidence": {
                    "months": len(current),
                    "records": sum(counts),
                    "peak_month": current[counts.index(max(counts))] if counts else None,
                    "peak_records": max(counts) if counts else 0,
                },
                "meaning": MEANING_PLACEHOLDER,
            }
        )

    for month in span:
        count = months.get(month, 0)
        mean = sum(running) / len(running) if running else 0.0
        surge = bool(running) and mean > 0 and (count >= mean * SURGE_FACTOR or (count == 0 < mean))
        if count <= QUIET_MAX:
            quiet_run += 1
        else:
            if quiet_run >= GAP_MONTHS and current:
                close(f"closed by silence: {quiet_run} consecutive months at or below {QUIET_MAX}")
                current, running = [], []
            elif surge and len(current) >= MIN_EPOCH_MONTHS:
                # The reason describes what ENDED this epoch — the month now being
                # opened, not one inside the epoch being closed. Naming the incoming
                # count while labelling the outgoing epoch read as if the quiet period
                # had itself surged.
                close(f"closed by surge in {month}: {count} records against a running mean of {mean:.1f}")
                current, running = [], []
            quiet_run = 0
        current.append(month)
        if count:
            running.append(count)
    close("end of observed span")
    return epochs


def _merge_preserving_meaning(derived: list[dict], existing_path: Path) -> list[dict]:
    """Carry forward every operator-authored meaning; the deriver never clobbers one."""
    if not existing_path.is_file():
        return derived
    try:
        prior = yaml.safe_load(existing_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return derived
    kept = {
        str(row.get("id")): row.get("meaning")
        for row in (prior.get("epochs") or [])
        if isinstance(row, dict) and row.get("meaning") not in (None, "", MEANING_PLACEHOLDER)
    }
    for row in derived:
        if row["id"] in kept:
            row["meaning"] = kept[row["id"]]
    return derived


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Derive epoch boundaries from hard signals only.")
    ap.add_argument("--write", action="store_true", help="write the store (default: dry-run)")
    args = ap.parse_args(argv)

    home = corpus_resolve.corpus_home()
    corpora = corpus_resolve.populated_corpora_including_undeclared(home)
    if not corpora:
        print(
            f"ERROR: no populated corpus under {home} — an unreachable corpus reads exactly "
            "like an empty one, so this refuses to derive rather than emit a confident vacuum",
            file=sys.stderr,
        )
        return 1

    corpus_months: Counter = Counter()
    per_corpus = {}
    for corpus in corpora:
        months = _thread_months(corpus)
        per_corpus[corpus.name] = sum(months.values())
        corpus_months.update(months)

    repo_months = _repo_months()
    series = {"corpus-thread-dates": corpus_months, "repo-activity": repo_months}

    doc = {
        "schema_version": 0.1,
        "generated_by": "scripts/derive-epochs.py",
        "provenance": "derived",
        "note": (
            "Boundaries are metadata arithmetic. `meaning: unknown` is the correct resting "
            "state and only the operator (or a cited corpus locator) may replace it — this "
            "deriver never writes one, and re-runs preserve any already present."
        ),
        "sources": {
            "corpus_home": str(home),
            "corpora": per_corpus,
            "repo_commits": sum(repo_months.values()),
        },
        "epochs": [],
    }
    for signal, months in series.items():
        if months:
            doc["epochs"].extend(_segment(months, signal))
    doc["epochs"].sort(key=lambda r: (r["start"], r["signal"]))

    if not args.write:
        print(f"corpus home : {home}")
        for name, total in per_corpus.items():
            print(f"  {name:<38} {total:>5} threads")
        print(f"repo commits: {sum(repo_months.values())}")
        print(f"\n{len(doc['epochs'])} epoch(s) derived — meaning stays 'unknown' by contract:\n")
        for row in doc["epochs"]:
            ev = row["evidence"]
            print(
                f"  {row['start']} -> {row['end']:<8} [{row['signal']:<19}] "
                f"{ev['records']:>5} records over {ev['months']:>2}mo   ({row['boundary_reason']})"
            )
        print(f"\n(dry-run — pass --write to land {OUT})")
        return 0

    doc["epochs"] = _merge_preserving_meaning(doc["epochs"], OUT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(OUT.parent, 0o700)
    OUT.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    os.chmod(OUT, 0o600)
    kept = sum(1 for r in doc["epochs"] if r["meaning"] != MEANING_PLACEHOLDER)
    print(f"WROTE {OUT}  —  {len(doc['epochs'])} epochs, {kept} with operator meaning preserved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
