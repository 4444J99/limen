#!/usr/bin/env python3
"""Derive BRANCHES.md from the authoritative branch-family registry."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio/governance/branch-families.yaml"
OUTPUT = ROOT / "BRANCHES.md"


def render(registry: dict) -> str:
    rows = registry["families"]
    lines = [
        "# Branch Constitution",
        "",
        "This document is generated from `institutio/governance/branch-families.yaml`; do not edit it directly.",
        "",
        "`main` is the protected production trunk and changes only through pull-request integration. "
        "Every non-trunk branch belongs to exactly one family below. Age is never a cleanup criterion: "
        "the family's receipt must be present before any cleanup consideration.",
        "",
        "| Family | Match | Owner | Intent | Required receipt |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {row['name']} | `{row['match']}` | {row['owner']} | {row['intent']} | {row['receipt']} |"
        for row in rows
    )
    receipts = registry.get("unintegrated_branch_receipts") or []
    if receipts:
        lines.extend(
            [
                "",
                "## Unintegrated branch receipts",
                "",
                "These branches have no pull-request record. Their exact-delta reconciliation is owned by the linked issue.",
                "",
                "| Branch | Family | Owner issue |",
                "|---|---|---|",
            ]
        )
        lines.extend(f"| `{row['branch']}` | {row['family']} | #{row['owner_issue']} |" for row in receipts)
    lines.extend(
        [
            "",
            "Successor branches retain a linked predecessor and integration receipt; they do not erase historical "
            "branches or pull requests. Stacked branches declare their merge order in their pull requests and are "
            "not independent `main` work.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    OUTPUT.write_text(render(registry), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
