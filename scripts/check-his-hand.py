#!/usr/bin/env python3
"""Validate the his-hand registry and derive diagnosis age.

The registry is the durable source of intent.  This predicate checks the shape that
downstream classifiers need, while keeping elapsed age derived rather than storing a
number that becomes stale after the commit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"open", "discharged", "retired", "needs_human", "optional", "blocked"}
REQUIRED = {"id", "label", "unlocks", "issue", "status", "diagnosed_at"}


def parse_time(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def load(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    levers = payload.get("levers") if isinstance(payload, dict) else payload
    if not isinstance(levers, list):
        raise ValueError("registry must contain a list at 'levers'")
    return levers


def evaluate(path: Path, now: datetime) -> tuple[list[str], dict]:
    errors: list[str] = []
    try:
        levers = load(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"registry unreadable: {exc}"], {"path": str(path), "total": 0, "diagnosed": 0}

    ids: set[str] = set()
    ages: list[int] = []
    for index, lever in enumerate(levers):
        prefix = f"lever[{index}]"
        if not isinstance(lever, dict):
            errors.append(f"{prefix}: entry is not an object")
            continue
        missing = sorted(REQUIRED - lever.keys())
        if missing:
            errors.append(f"{prefix} {lever.get('id', '<unnamed>')}: missing {','.join(missing)}")
        lid = lever.get("id")
        if not isinstance(lid, str) or not lid.strip():
            errors.append(f"{prefix}: id must be a nonempty string")
        elif lid in ids:
            errors.append(f"{prefix} {lid}: duplicate id")
        else:
            ids.add(lid)
        status = lever.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"{prefix} {lid}: invalid status {status!r}")
        stamp = lever.get("diagnosed_at")
        if stamp is None:
            continue
        try:
            diagnosed = parse_time(str(stamp))
        except ValueError as exc:
            errors.append(f"{prefix} {lid}: invalid diagnosed_at: {exc}")
            continue
        if diagnosed > now:
            errors.append(f"{prefix} {lid}: diagnosed_at is in the future")
        ages.append(max(0, (now.date() - diagnosed.date()).days))

    census = {
        "path": str(path),
        "total": len(levers),
        "unique_ids": len(ids),
        "diagnosed": len(ages),
        "days_since_diagnosed_min": min(ages) if ages else None,
        "days_since_diagnosed_max": max(ages) if ages else None,
        "statuses": {
            status: sum(1 for lever in levers if isinstance(lever, dict) and lever.get("status") == status)
            for status in sorted(STATUSES)
        },
        "violations": len(errors),
    }
    return errors, census


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit non-zero on a registry violation")
    parser.add_argument("--json", action="store_true", dest="json_output", help="print the census as JSON")
    parser.add_argument("--now", help="UTC reference time for deterministic age checks")
    parser.add_argument("--registry", default=os.environ.get("LIMEN_HIS_HAND_LEVERS", "his-hand-levers.json"))
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    errors, census = evaluate(Path(args.registry), now)
    if args.json_output:
        print(json.dumps({"census": census, "violations": errors}, indent=2, sort_keys=True))
    else:
        print(f"his-hand: {census['total']} levers, diagnosed={census['diagnosed']}, violations={len(errors)}")
        for error in errors:
            print(f"FAIL  {error}")
    return 1 if errors and args.check else 0


if __name__ == "__main__":
    sys.exit(main())
