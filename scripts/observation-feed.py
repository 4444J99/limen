#!/usr/bin/env python3
"""observation-feed.py — Unified Observation Organ Telemetry Feed Engine.

Collects and emits live system vitals, Bifrons star<->contribution metrics,
and Observatory legibility metrics into an append-only feed.

Schema: limen.observation.feed.v1

Usage:
  python3 scripts/observation-feed.py --emit     # collect & append to feed.jsonl + feed-latest.json
  python3 scripts/observation-feed.py --check    # validate existing feed files against schema
  python3 scripts/observation-feed.py --json     # emit JSON to stdout
  python3 scripts/observation-feed.py --quiet    # suppress stdout on success
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure cli/src is on sys.path
ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.observation import (  # noqa: E402
    SCHEMA_V1,
    check_feed,
    emit_feed_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Observation Organ Telemetry Feed Engine (schema limen.observation.feed.v1)."
    )
    parser.add_argument(
        "--emit",
        action="store_true",
        help="Collect live telemetry and emit a record to logs/observation/feed.jsonl and feed-latest.json (default action).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate logs/observation/feed-latest.json and feed.jsonl against schema.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Format output as JSON.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress informational stdout on success.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Custom root directory (defaults to repo root).",
    )

    args = parser.parse_args()
    root = args.root or ROOT

    # If neither --emit nor --check is explicitly given, default to --emit
    mode = "check" if args.check and not args.emit else "emit"

    if mode == "check":
        ok, errors = check_feed(base_dir=root)
        if not ok:
            if args.json:
                print(json.dumps({"ok": False, "errors": errors}, indent=2))
            else:
                print(f"FAIL: observation feed check failed ({len(errors)} error(s)):", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
            return 1
        if not args.quiet:
            if args.json:
                print(json.dumps({"ok": True, "schema": SCHEMA_V1}))
            else:
                print(f"observation-feed: check passed (schema={SCHEMA_V1})")
        return 0

    # Mode: emit
    try:
        record, jsonl_path, latest_path = emit_feed_record(base_dir=root)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"FAIL: failed to emit observation feed record: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        if args.json:
            print(json.dumps(record, indent=2))
        else:
            v_action = record.get("vitals", {}).get("action", "ok")
            b_stars = record.get("bifrons", {}).get("stars", 0)
            o_hero = record.get("observatory", {}).get("hero")
            status = record.get("status", "ok")
            print(
                f"observation-feed: emitted {record.get('schema')} "
                f"[status={status}, vitals={v_action}, bifrons_stars={b_stars}, hero={o_hero}] -> {latest_path}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
