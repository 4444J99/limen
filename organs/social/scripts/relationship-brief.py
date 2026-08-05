#!/usr/bin/env python3
"""Relationship-Posture Brief generator.

Reads a Koinonia engagement YAML and prints a human-readable
relationship-posture brief.

Usage:
  python organs/social/scripts/relationship-brief.py organs/social/engagements/derek.yaml
  python organs/social/scripts/relationship-brief.py organs/social/engagements/derek.yaml --out report.md
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


def _fmt_val(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        return "\n".join(f"  - {item}" for item in v)
    if isinstance(v, dict):
        return "\n".join(f"  {k}: {_fmt_val(iv)}" for k, iv in v.items())
    return str(v)


def generate_brief(doc: dict[str, Any], path: Path) -> str:
    member = doc.get("member", {})
    mandate = doc.get("mandate", {})
    standing = doc.get("standing", {})
    standard = doc.get("standard", {})
    governance = doc.get("governance", {})
    artifacts = doc.get("artifacts", {})

    lines: list[str] = []
    lines.append("# Relationship-Posture Brief")
    lines.append("")
    lines.append(f"**Person:** {member.get('name', '(unnamed)')}  ")
    lines.append(f"**Identifier:** `{member.get('identifier', '—')}`  ")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime(FMT)}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 1. Member (person)")
    lines.append("")
    lines.append(f"**Name:** {member.get('name', '(unnamed)')}")
    lines.append(f"**Identifier:** `{member.get('identifier', '—')}`")
    ctx = member.get("context", "")
    if ctx:
        lines.append(f"**Context:** {ctx}")
    note = member.get("note", "")
    if note:
        lines.append(f"**Note:** {note}")
    lines.append("")

    lines.append("## 2. Mandate (relationship)")
    lines.append("")
    lines.append(f"**Relationship:** {mandate.get('relationship', '(not specified)')}")
    why = mandate.get("why_it_matters", "")
    if why:
        lines.append(f"**Why it matters:** {why}")
    lines.append("")

    lines.append("## 3. Standing (tie strength)")
    lines.append("")
    cur = standing.get("current", "(not set)")
    lines.append(f"**Current standing:** `{cur}`")
    warmth = standing.get("warmth", "")
    if warmth:
        lines.append(f"**Warmth:** {warmth}")
    history = standing.get("history", [])
    if history:
        lines.append("**History:**")
        for h in history:
            period = h.get("period", "")
            state = h.get("state", "")
            notes = h.get("notes", "")
            lines.append(f"  - {period}: **{state}** — {notes}")
    lines.append("")

    lines.append("## 4. Standard (reciprocity norm)")
    lines.append("")
    lines.append(f"**Reciprocity norm:** {standard.get('reciprocity_norm', '(not set)')}")
    cadence = standard.get("expected_cadence", "")
    if cadence:
        lines.append(f"**Expected cadence:** {cadence}")
    reply = standard.get("reply_window", "")
    if reply:
        lines.append(f"**Reply window:** {reply}")
    boundaries = standard.get("boundaries", [])
    if boundaries:
        lines.append("**Boundaries:**")
        for b in boundaries:
            lines.append(f"  - {b}")
    owed = standard.get("owed_replies", [])
    if owed:
        lines.append("**Owed replies:**")
        for o in owed:
            lines.append(f"  - {o}")
    care = standard.get("care_pattern", "")
    if care:
        lines.append(f"**Care pattern:** {care}")
    lines.append("")

    lines.append("## 5. Governance (authority and consent)")
    lines.append("")
    lines.append(f"**Manual mode:** {'yes' if governance.get('manual_mode') else 'NO — WARNING'}  ")
    lines.append(f"**Human:** {governance.get('human', '(not set)')}")
    consent = governance.get("consent", [])
    if consent:
        lines.append("**Consent:**")
        for c in consent:
            lines.append(f"  - {c}")
    requires = governance.get("requires_human", [])
    if requires:
        lines.append("**Requires human:**")
        for r in requires:
            lines.append(f"  - {r}")
    never = governance.get("never_autonomous", [])
    if never:
        lines.append("**Never autonomous:**")
        for n in never:
            lines.append(f"  - {n}")
    gates = governance.get("human_gates", [])
    if gates:
        lines.append(f"**Human gates:** `{', '.join(gates)}`")
    lines.append("")

    lines.append("## Artifacts and next step")
    lines.append("")
    nro = artifacts.get("next_reviewable_output", "(not set)")
    lines.append(f"**Next reviewable output:** {nro}")
    evidence = artifacts.get("evidence", [])
    if evidence:
        lines.append("**Evidence:**")
        for e in evidence:
            lines.append(f"  - {e}")
    updated = doc.get("updated", "")
    if updated:
        lines.append("")
        lines.append(f"*Last updated: {updated}*")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a relationship-posture brief")
    parser.add_argument("path", type=Path, help="Path to engagement YAML")
    parser.add_argument("--out", type=Path, help="Write output to file instead of stdout")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 1

    try:
        doc = yaml.safe_load(args.path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"ERROR: could not read {args.path}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(doc, dict):
        print(f"ERROR: {args.path} is not a YAML mapping", file=sys.stderr)
        return 1

    brief = generate_brief(doc, args.path)

    if args.out:
        args.out.write_text(brief, encoding="utf-8")
        print(f"Brief written to {args.out}")
    else:
        print(brief)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
