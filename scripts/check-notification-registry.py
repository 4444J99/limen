#!/usr/bin/env python3
"""Static parity for notification identities and heartbeat retirement ownership."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

try:
    import yaml
except ModuleNotFoundError:  # optional outside the managed Limen environment
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "institutio" / "governance" / "notification-events.limen.json"
OWNERSHIP = ROOT / "institutio" / "governance" / "heartbeat-ownership.json"
SENSORS = ROOT / "institutio" / "governance" / "sensors.yaml"
PRODUCER_ID_RE = re.compile(r"stable_id\s*=\s*[\"'](limen\.[a-z0-9_.-]+)[\"']")
EVENT_LITERAL_RE = re.compile(r"[\"'](limen\.[a-z0-9_.-]+)[\"']")
NON_EVENT_PROTOCOL_IDS = {"limen.notification_events.v1"}


def main() -> int:
    if yaml is None:
        print("notification-registry: SKIP — PyYAML unavailable")
        return 0
    errors: list[str] = []
    registry = json.loads(REGISTRY.read_text())
    events = registry.get("events") or {}
    required = {"class", "severity", "owner", "privacy", "channels", "dedupe_key", "recovery", "title", "templates"}
    for stable_id, definition in events.items():
        missing = required - set(definition)
        if missing:
            errors.append(f"{stable_id}: missing {sorted(missing)}")
        if not stable_id.startswith("limen."):
            errors.append(f"{stable_id}: wrong namespace")
    discovered: dict[str, set[str]] = {}
    undeclared_calls: set[str] = set()
    for base in (ROOT / "scripts", ROOT / "cli" / "src"):
        for path in base.rglob("*.py"):
            if path == Path(__file__):
                continue
            source = path.read_text(errors="ignore")
            for stable_id in events:
                if f'"{stable_id}"' in source or f"'{stable_id}'" in source:
                    discovered.setdefault(stable_id, set()).add(str(path.relative_to(ROOT)))
            undeclared_calls.update(PRODUCER_ID_RE.findall(source))
            if "emit_event_v1" in source:
                undeclared_calls.update(EVENT_LITERAL_RE.findall(source))
    undeclared = undeclared_calls - set(events) - NON_EVENT_PROTOCOL_IDS
    if undeclared:
        errors.append(f"undeclared producer IDs: {sorted(undeclared)}")
    unreachable = set(events) - set(discovered)
    if unreachable:
        errors.append(f"unreachable registry IDs: {sorted(unreachable)}")
    ownership = json.loads(OWNERSHIP.read_text()).get("rungs") or {}
    sensors = yaml.safe_load(SENSORS.read_text()).get("sensors") or {}
    heartbeat = {name for name, row in sensors.items() if "heartbeat" in (row.get("source") or [])}
    if heartbeat != set(ownership):
        errors.append(
            f"heartbeat ownership mismatch missing={sorted(heartbeat - set(ownership))} extra={sorted(set(ownership) - heartbeat)}"
        )
    for name, row in ownership.items():
        if not isinstance(row.get("timeout_seconds"), int) or row["timeout_seconds"] <= 0:
            errors.append(f"{name}: invalid timeout")
        for field in ("owner", "receipt", "predicate"):
            if not row.get(field):
                errors.append(f"{name}: missing {field}")
    if errors:
        print("notification-registry: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"notification-registry: PASS — {len(events)} events, {len(heartbeat)} retired heartbeat rungs owned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
