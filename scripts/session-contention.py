#!/usr/bin/env python3
"""session-contention — the receipt IF-SESSION-NON-CONTENTION is measured by.

THE IDEAL: "an interactive session's cwd is an isolated, non-recycled worktree; the fleet never
rebases or cleans the tree a live session is working in."

Contention is an EVENT, not a state — nothing on disk afterwards distinguishes "was rebased under
a live session" from "was rebased". So the ideal was unmeasurable until something recorded the
event. This is that something.

  probe   --root PATH   exit 0 free / 1 occupied. What sync-release.sh consults before it
                        rewrites the live checkout. Reports a FOREIGN live process only, and
                        never counts a session in a nested worktree (isolated by design).
                        A third VERDICT (not a third exit code) says the probe went blind:
                        "probe UNAVAILABLE — guard disarmed". It exits 0 like `free`, because
                        fail-open is the deliberate direction here, but it no longer says
                        `free` — a disarmed guard that reports itself healthy is how this
                        organ's own blindness stayed invisible.
  record  --root PATH --pid N --action ACTION
                        append one incident to logs/session-contention.jsonl, ONSET-DEDUPED:
                        a session legitimately sitting in the live checkout for six hours is
                        one incident, not one per beat. Fail-open and fast — this runs inside
                        the beat and must never be able to stop it.
  ship                  promote unshipped incidents into the committed ledger via ship-docs.sh.
                        Separate from `record` on purpose: recording must be instant and local,
                        while durability is a git operation that can be slow, can fail, and can
                        be retried on the next beat without losing anything.

WHY TWO STAGES. Rule #2 says nothing is local-only, so the incident must reach git. But the
recorder runs inside sync-release.sh, whose whole job is to keep the live checkout clean —
committing from there would have the organ fight the daemon for the tree it is guarding. Record
local, ship separately, and the durable record is a normal PR like every other beat artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))

LOG_REL = "logs/session-contention.jsonl"
LEDGER_REL = "docs/receipts/session-contention-ledger.json"
SHIP = "scripts/ship-docs.sh"
SCHEMA = "limen.session_contention_ledger.v1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _occupancy(root: Path) -> tuple[int | None, bool]:
    """`(occupant_pid, probe_available)`. Fails OPEN — see liveness.py.

    Availability is carried separately because all three ways this can go blind — an unimportable
    package, an unresolvable root, a process table that could not be read at all — otherwise
    answer `None`, which is also the answer for a genuinely free tree. Fail-open is the right
    direction; fail-open in the SAME WORDS as success is what let a disarmed guard read as a
    healthy one on 2026-08-06.
    """
    try:
        from limen.conduct.liveness import live_checkout_occupancy
    except ImportError:
        return None, False  # fail open: an unimportable probe accuses no one — and says so
    return live_checkout_occupancy(root)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # a torn line is not a reason to lose the rest
    return rows


def _incident_digest(row: dict) -> str:
    payload = {key: value for key, value in row.items() if key != "shipped"}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _incident_key(row: dict) -> str:
    """Return the recorded event ID, with a stable digest for legacy rows."""
    event_id = row.get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    return f"legacy-{_incident_digest(row)}"


def cmd_probe(args: argparse.Namespace) -> int:
    root = Path(args.root or ROOT)
    pid, available = _occupancy(root)
    if not available:
        # EXIT 0, DELIBERATELY. The status is this probe's fail-open direction and nothing else:
        # "safe to proceed". A distinct non-zero here would read as "stop" to any consumer that
        # tests the status, silently inverting the guard into fail-CLOSED on exactly the hosts
        # where it is broken — the outcome liveness.py spends a paragraph refusing. The TEXT is
        # the verdict (sync-release.sh parses it and ignores the status), so the text is where
        # blindness is reported. It deliberately contains no "OCCUPIED by pid", so the guard
        # stays empty and behaviour is byte-identical to before this distinction existed.
        print(f"session-contention: {root} probe UNAVAILABLE — guard disarmed, proceeding fail-open")
        return 0
    if pid is None:
        print(f"session-contention: {root} free")
        return 0
    print(f"session-contention: {root} OCCUPIED by pid {pid}")
    return 1


def cmd_record(args: argparse.Namespace) -> int:
    root = str(Path(args.root or ROOT))
    log = ROOT / LOG_REL

    # Onset dedup: the same (root, pid) still holding the tree is the SAME incident. Without
    # this a session working normally for an afternoon manufactures one incident per beat, the
    # count becomes a measure of session duration rather than of contention, and the ideal's
    # number stops meaning anything.
    for row in reversed(_read_jsonl(log)):
        if row.get("root") == root and row.get("pid") == args.pid:
            print(f"session-contention: incident already open for pid {args.pid} — not re-recording")
            return 0
        break

    incident = {
        "event_id": f"contention-{uuid.uuid4()}",
        "observed_at": _now(),
        "root": root,
        "pid": args.pid,
        "action": args.action,
        "shipped": False,
    }
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(incident, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"session-contention: could not record ({exc}) — failing open")
        return 0
    print(f"session-contention: recorded {args.action} at {root} (pid {args.pid})")
    return 0


def cmd_ship(args: argparse.Namespace) -> int:
    log = ROOT / LOG_REL
    rows = _read_jsonl(log)
    unshipped = [r for r in rows if not r.get("shipped")]
    if not unshipped:
        print("session-contention: nothing to ship — no unrecorded incidents")
        return 0

    ledger_path = ROOT / LEDGER_REL
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except ValueError:
            print(f"session-contention: {LEDGER_REL} is not valid JSON — refusing to overwrite it")
            return 1
    else:
        ledger = {"schema": SCHEMA, "incidents": []}

    existing = list(ledger.get("incidents") or [])
    candidates = existing + [{k: v for k, v in r.items() if k != "shipped"} for r in unshipped]
    incidents: list[dict] = []
    seen: dict[str, str] = {}
    for row in candidates:
        key = _incident_key(row)
        digest = _incident_digest(row)
        if key in seen:
            if seen[key] != digest:
                print(
                    "session-contention: event_id collision in incident evidence "
                    f"({key}) — refusing to rewrite the ledger"
                )
                return 1
            continue
        seen[key] = digest
        incidents.append(row)
    if incidents != existing:
        ledger["generated_at"] = _now()
    ledger["incidents"] = incidents
    ledger["incident_count"] = len(incidents)
    ledger["schema"] = SCHEMA

    if args.dry_run:
        print(json.dumps(ledger, indent=2, sort_keys=True))
        return 0

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    msg = f"docs(contention): record session-contention incident ({ledger['incident_count']} total)"
    ship = subprocess.run(
        ["bash", str(ROOT / SHIP), "session-contention-incident", msg, LEDGER_REL],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    print(ship.stdout.strip() or ship.stderr.strip())
    if ship.returncode != 0:
        print("session-contention: ship failed — incidents stay unshipped and retry next beat")
        return 1

    for row in rows:
        row["shipped"] = True
    log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    print(f"session-contention: shipped {len(unshipped)} incident(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="exit 0 when the live checkout is free, 1 when occupied")
    p.add_argument("--root", default=None)
    p.set_defaults(fn=cmd_probe)

    r = sub.add_parser("record", help="append one onset-deduped incident")
    r.add_argument("--root", default=None)
    r.add_argument("--pid", type=int, required=True)
    r.add_argument("--action", required=True, help="what the daemon declined to do, e.g. skipped-reset")
    r.set_defaults(fn=cmd_record)

    s = sub.add_parser("ship", help="promote unshipped incidents into the committed ledger")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_ship)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
