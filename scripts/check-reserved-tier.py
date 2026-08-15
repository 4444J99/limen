#!/usr/bin/env python3
"""check-reserved-tier.py — reserved-tier accounting that binds EVERY lane, not one.

`docs/fable-allotment.md` declares Fable a reserved tier: a run needs a written
`scripts/fable-allotment.py accept ...` receipt before it starts. That rule is
estate-wide in prose and was enforced Claude-lane-only in code, on both axes —
measured 2026-08-15:

* `fable-allotment.py::_fable_weekly_tokens()` sums Fable billable tokens **from
  Claude Code transcripts** (`_transcripts_dir()`). A copilot session on
  `claude-fable-5` contributes 0 to `spent_pct`, `over_cap`, and every downstream
  downgrade.
* `claude-workflow-guard.py` resolves transcripts through `harness_paths` alone, so
  `audit-transcript` cannot be pointed at a copilot/codex/opencode session at all.
* `AGENTS.md` § Agent-Specific Notes covers Codex/Copilot/OpenCode/Gemini/Agy with
  zero mentions of Fable, acceptance, or tier.

The same sweep found copilot running `claude-fable-5` in 3 of its 5 substantive
sessions, and `logs/fable-acceptance/` empty. Nothing was wrong with the copilot
lane; the rule had only ever been written for one lane's transcript store.

WHAT THIS READS. Only `logs/vendor-insights/<lane>/index.json` — refreshed every 24h
by the `insight-cross-vendor` beat sensor, and already carrying a per-session `models`
list. No vendor store is opened here: store access belongs to
`scripts/insight-cross-vendor-ingest.py`, which owns every path (`VENDOR_REGISTRY`),
and re-deriving one would fork the substrate.

WHY IT PARTITIONS. Three lanes (antigravity, opencode, gemini) record NO model
identity at all. Counting those sessions as compliant is `reference_state`'s "green
through absence" one axis over: a lane that never used a reserved tier and a lane
whose store cannot say read IDENTICALLY. So every session is accounted through
`limen.bucket_partition` against the DECLARED denominator (`meta.total_in_window`,
never `len(sessions)` — the antigravity index is capped at 40 of 157), and lanes that
are structurally blind are recorded in a shrink-only baseline rather than silently
passing. A lane that goes blind AFTER baselining fails.

Exit 0 ⟺ no lane ran a reserved tier without a covering acceptance receipt, and no
NEW blindness appeared.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.bucket_partition import partition  # noqa: E402

INDEX_ROOT = Path(os.environ.get("LIMEN_VENDOR_INSIGHTS_DIR") or ROOT / "logs" / "vendor-insights")
RECEIPTS = Path(os.environ.get("LIMEN_FABLE_RECEIPTS_DIR") or ROOT / "logs" / "fable-acceptance")
BASELINE = ROOT / "institutio" / "governance" / "reserved-tier-blind-baseline.txt"

#: Tiers requiring a written acceptance receipt before the run starts.
RESERVED_TIERS = tuple(
    t.strip() for t in os.environ.get("LIMEN_RESERVED_TIERS", "claude-fable-5").split(",") if t.strip()
)

#: How long an acceptance receipt covers runs that start after it. The allotment
#: itself is reckoned per ISO-week, so a 7-day cover matches the ledger it defends.
COVER_DAYS = int(os.environ.get("LIMEN_RESERVED_TIER_COVER_DAYS", "7"))

ACCEPTED = "accepted"
UNACCEPTED = "unaccepted"
NO_RESERVED_TIER = "no-reserved-tier"
BLIND = "blind"

BASELINE_HEADER = """# reserved-tier-blind-baseline.txt — lanes whose session store records NO model identity.
#
# Held OUT of scripts/check-reserved-tier.py. Same shrink-only ratchet the estate already
# uses for note links, root manifest, effectors and runners: history is recorded, never
# rewritten, and every NEW blind lane is held.
#
# A line leaves this file exactly one way: by the lane's store gaining model identity (or
# the ingest adapter learning to read it). A stale line — the lane now reports models —
# FAILS, so the baseline can only shrink. Never add a line to silence a lane that used to
# report and stopped: that is a regression, and this ratchet exists to catch it.
#
# Being on this list is NOT permission. It means a reserved-tier run in that lane cannot
# currently be detected at all, which is strictly worse than a violation you can see.
"""


def _load_baseline() -> set[str]:
    try:
        return {
            line.strip()
            for line in BASELINE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    except OSError:
        return set()


def _parse_ts(raw: object) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _acceptance_windows() -> list[tuple[dt.datetime, dt.datetime, str]]:
    """Every acceptance receipt as a (start, end, name) cover window."""
    windows: list[tuple[dt.datetime, dt.datetime, str]] = []
    if not RECEIPTS.is_dir():
        return windows
    for path in sorted(RECEIPTS.glob("*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        start = _parse_ts(receipt.get("created_at"))
        if start is None:
            continue
        windows.append((start, start + dt.timedelta(days=COVER_DAYS), path.name))
    return windows


def _covered(started: dt.datetime | None, windows: list[tuple[dt.datetime, dt.datetime, str]]) -> str | None:
    """The receipt covering a run, or None. A run with no start time is NOT covered.

    Acceptance is written BEFORE the run; a run whose start cannot be established
    cannot be shown to postdate any receipt, and unprovable is not the same as fine.
    """
    if started is None:
        return None
    for start, end, name in windows:
        if start <= started <= end:
            return name
    return None


def classify_lane(index: dict, windows: list[tuple[dt.datetime, dt.datetime, str]]) -> tuple[dict, dict, dict]:
    """Return (assignments, evidence, meta) for one lane's index."""
    sessions = index.get("sessions") or []
    assignments: dict[str, str] = {}
    evidence: dict[str, dict] = {}
    for session in sessions:
        if not isinstance(session, dict):
            continue
        sid = str(session.get("id") or "")
        if not sid:
            continue
        models = session.get("models")
        if not models:
            # No model identity recorded — deliberately UNASSIGNED so the partition
            # carries it as residual rather than as a clean bill of health.
            continue
        reserved = sorted({m for m in models if str(m) in RESERVED_TIERS})
        if not reserved:
            assignments[sid] = NO_RESERVED_TIER
            continue
        started = _parse_ts(session.get("started_at"))
        receipt = _covered(started, windows)
        assignments[sid] = ACCEPTED if receipt else UNACCEPTED
        evidence[sid] = {"tiers": reserved, "started_at": session.get("started_at"), "receipt": receipt}
    return assignments, evidence, index.get("meta") or {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit the raw accounting")
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the currently-blind lanes (bootstrap only — never to silence a fresh one)",
    )
    args = ap.parse_args(argv)

    if not INDEX_ROOT.is_dir():
        print(f"check-reserved-tier: no vendor index at {INDEX_ROOT} — run the insight-cross-vendor beat first")
        return 0

    windows = _acceptance_windows()
    baseline = _load_baseline()
    lanes: dict[str, dict] = {}
    blind_now: set[str] = set()
    violations: list[str] = []

    for index_path in sorted(INDEX_ROOT.glob("*/index.json")):
        lane = index_path.parent.name
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        assignments, evidence, meta = classify_lane(index, windows)
        sessions = [s for s in (index.get("sessions") or []) if isinstance(s, dict) and s.get("id")]
        if not sessions:
            continue
        declared = meta.get("total_in_window")
        if not isinstance(declared, int):
            declared = len(sessions)

        result = partition(
            declared_total=declared,
            candidates=[str(s["id"]) for s in sessions],
            assignments=assignments,
        )
        if result.unaccounted and not any(s.get("models") for s in sessions):
            blind_now.add(lane)

        unaccepted = [sid for sid, bucket in assignments.items() if bucket == UNACCEPTED]
        for sid in unaccepted:
            info = evidence.get(sid, {})
            violations.append(
                f"{lane}/{sid}: ran {', '.join(info.get('tiers', []))} with no covering acceptance receipt"
            )

        lanes[lane] = {
            "declared_total": declared,
            "shown": len(sessions),
            "capped": bool(meta.get("capped")),
            "counts": dict(result.counts),
            "unaccounted": len(result.unaccounted),
            "unenumerated": result.unenumerated,
            "blind": lane in blind_now,
            "unaccepted_sessions": unaccepted,
            "report": result.report(),
        }

    if args.write_baseline:
        BASELINE.write_text(BASELINE_HEADER + "\n".join(sorted(blind_now)) + "\n", encoding="utf-8")
        print(f"check-reserved-tier: baseline written — {len(blind_now)} blind lane(s) recorded")
        return 0

    fresh_blind = sorted(blind_now - baseline)
    stale_blind = sorted(baseline - blind_now)

    if args.json:
        print(json.dumps({"lanes": lanes, "violations": violations, "fresh_blind": fresh_blind}, indent=2))

    total_declared = sum(v["declared_total"] for v in lanes.values())
    total_shown = sum(v["shown"] for v in lanes.values())
    print(
        f"check-reserved-tier: {len(lanes)} lane(s) · {total_shown} session(s) read of "
        f"{total_declared} in window · {len(windows)} acceptance receipt(s) on disk"
    )
    for lane, data in sorted(lanes.items()):
        flags = []
        if data["capped"]:
            flags.append(f"CAPPED {data['shown']}/{data['declared_total']}")
        if data["blind"]:
            flags.append("BLIND (store records no model identity)")
        summary = " · ".join(f"{n}={c}" for n, c in sorted(data["counts"].items())) or "no classifiable session"
        tail = f"  [{'; '.join(flags)}]" if flags else ""
        print(f"  {lane:<16} {summary}{tail}")

    rc = 0
    for line in violations:
        print(f"FAIL  {line}")
        rc = 1
    for lane in fresh_blind:
        print(
            f"FAIL  lane '{lane}' records no model identity and is not baselined — a reserved-tier "
            f"run there cannot be detected at all. Teach the ingest adapter to read models, or "
            f"record the blindness explicitly (--write-baseline)."
        )
        rc = 1
    for lane in stale_blind:
        print(
            f"FAIL  lane '{lane}' is baselined as blind but now reports model identity — the "
            f"baseline is shrink-only; drop the line from {BASELINE.name}."
        )
        rc = 1

    if rc == 0:
        blind_note = f" ({len(baseline)} lane(s) baselined blind — recorded, not forgiven)" if baseline else ""
        print(f"check-reserved-tier: OK — no unaccepted reserved-tier run in any lane{blind_note}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
