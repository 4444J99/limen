#!/usr/bin/env python3
"""Triage Dashboard generator for Koinonia social organ.

Reads all engagement YAMLs from the engagements directory and produces a
sorted fleet-wide triage view: which relationships need care, replies,
repair, or attention — and which are current, dormant, or protected.

Usage:
  python organs/social/scripts/triage-dashboard.py
  python organs/social/scripts/triage-dashboard.py --out dashboard.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


FMT = "%Y-%m-%dT%H:%M:%SZ"
STANDING_ORDER = {
    "STRAINED": 0,
    "BROKEN": 1,
    "PROTECTED": 2,
    "ACTIVE": 3,
    "WARM": 4,
    "DORMANT": 5,
}


def _standing_rank(standing: str) -> int:
    return STANDING_ORDER.get(standing.upper(), 99)


def _standing_priority_label(standing: str) -> str:
    labels = {
        "STRAINED": "REPAIR NEEDED",
        "BROKEN": "CLOSED / REPAIR",
        "PROTECTED": "BOUNDARY-ACTIVE",
        "ACTIVE": "CURRENT",
        "WARM": "MAINTAIN",
        "DORMANT": "RECONNECT?",
    }
    return labels.get(standing.upper(), str(standing).upper())


def _read_engagements(engagements_dir: Path) -> list[tuple[str, dict[str, Any], list[str]]]:
    results: list[tuple[str, dict[str, Any], list[str]]] = []
    for path in sorted(engagements_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        violations: list[str] = []
        member = doc.get("member", {})
        identifier = member.get("identifier", path.stem) if isinstance(member, dict) else path.stem
        results.append((identifier, doc, violations))
    return results


def generate_dashboard(base: Path) -> str:
    engagements_dir = base / "engagements"
    if not engagements_dir.is_dir():
        return f"ERROR: engagements directory not found: {engagements_dir}\n"

    raw = _read_engagements(engagements_dir)
    if not raw:
        return "No engagement records found.\n"

    engagements = []
    for identifier, doc, violations in raw:

        def _g(key: str, sub: str | None = None) -> Any:
            v = doc.get(key, {})
            if isinstance(v, dict) and sub:
                return v.get(sub, "")
            if isinstance(v, dict):
                return v
            return v

        member = doc.get("member", {}) or {}
        mandate = doc.get("mandate", {}) or {}
        standing = doc.get("standing", {}) or {}
        standard = doc.get("standard", {}) or {}
        governance = doc.get("governance", {}) or {}
        artifacts = doc.get("artifacts", {}) or {}

        standing_raw = standing.get("current", "") if isinstance(standing, dict) else ""
        standing_val = str(standing_raw).upper()

        engagements.append({
            "identifier": identifier,
            "name": member.get("name", identifier) if isinstance(member, dict) else identifier,
            "relationship": mandate.get("relationship", "") if isinstance(mandate, dict) else "",
            "standing": standing_val,
            "standing_label": _standing_priority_label(standing_val),
            "standing_rank": _standing_rank(standing_val),
            "warmth": standing.get("warmth", "") if isinstance(standing, dict) else "",
            "owed_replies": (standard.get("owed_replies", []) if isinstance(standard, dict) else []),
            "care_pattern": standard.get("care_pattern", "") if isinstance(standard, dict) else "",
            "next_output": artifacts.get("next_reviewable_output", "") if isinstance(artifacts, dict) else "",
            "manual_mode": (governance.get("manual_mode") is True if isinstance(governance, dict) else False),
            "human_gates": (governance.get("human_gates", []) if isinstance(governance, dict) else []),
            "never_autonomous": (governance.get("never_autonomous", []) if isinstance(governance, dict) else []),
            "violations": violations,
            "doc": doc,
        })

    engagements.sort(key=lambda e: (e["standing_rank"], e["name"]))

    lines: list[str] = []
    lines.append("# Koinonia — Triage Dashboard")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime(FMT)}  ")
    lines.append(f"**Engagements:** {len(engagements)}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Fleet Overview")
    lines.append("")
    lines.append("| Person | Relationship | Standing | Warmth | Owed Replies | Next Gate |")
    lines.append("|---|---|---|---|---|---|")
    for e in engagements:
        name = e["name"]
        rel = e["relationship"]
        st = f"**{e['standing']}** ({e['standing_label']})"
        warmth = e["warmth"][:50] + "..." if len(e["warmth"]) > 50 else e["warmth"]
        owed = "; ".join(e["owed_replies"][:3]) if e["owed_replies"] else "—"
        if len(owed) > 60:
            owed = owed[:57] + "..."
        gates = ", ".join(e["human_gates"]) if e["human_gates"] else "—"
        if len(gates) > 60:
            gates = gates[:57] + "..."
        lines.append(f"| {name} | {rel} | {st} | {warmth} | {owed} | {gates} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    for e in engagements:
        lines.append(f"## {e['name']} — {e['standing']}")
        lines.append("")
        lines.append(f"- **Relationship:** {e['relationship']}")
        lines.append(f"- **Standing:** {e['standing']} — {e['standing_label']}")
        if e["warmth"]:
            lines.append(f"- **Warmth:** {e['warmth']}")
        if e["owed_replies"]:
            lines.append("- **Owed replies:**")
            for o in e["owed_replies"]:
                lines.append(f"  - {o}")
        if e["care_pattern"]:
            lines.append(f"- **Care pattern:** {e['care_pattern']}")
        if e["next_output"]:
            lines.append(f"- **Next reviewable:** {e['next_output']}")
        if e["manual_mode"]:
            lines.append(f"- **Human gates:** {', '.join(e['human_gates'])}")
        if e["never_autonomous"]:
            lines.append("- **Never autonomous:**")
            for n in e["never_autonomous"]:
                lines.append(f"  - {n}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Koinonia triage dashboard")
    parser.add_argument("--out", type=Path, help="Write output to file instead of stdout")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent.parent
    dashboard = generate_dashboard(base)

    if args.out:
        args.out.write_text(dashboard, encoding="utf-8")
        print(f"Dashboard written to {args.out}")
    else:
        print(dashboard)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
