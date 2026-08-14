#!/usr/bin/env python3
"""Focused non-circular regression check for PSP-P03-W02."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE = ROOT / "docs/positioning/portfolio-information-architecture.md"
FRONTDOOR = ROOT / "docs/positioning/_frontdoor.md"

EXPECTED_BLOCKS = {
    "Identity and audience orientation": ("J-ENTRY", "L1"),
    "Client decision door": ("J-C1", "L1"),
    "Recruiter role door": ("J-R1", "L1"),
    "Flagship proof collection": ("J-C2", "L2"),
    "Collaboration and handoff note": ("J-R2", "L2"),
    "Collaborative-systems index": ("J-R2", "L2"),
    "Product-operating readiness index": ("J-O1", "L3"),
}


def map_rows(document: str) -> dict[str, tuple[str, str]]:
    section = document.split("## Public content map", 1)[1].split(
        "## Front-door CTA invariant", 1
    )[0]
    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "Public-content class":
            continue
        assert len(cells) == 6, line
        audience_job, level = cells[2], cells[3]
        assert re.fullmatch(r"J-(?:ENTRY|C[12]|R[12]|O1)", audience_job), line
        assert level in {"L1", "L2", "L3"}, line
        rows[cells[0]] = (audience_job, level)
    return rows


def main() -> None:
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    frontdoor = FRONTDOOR.read_text(encoding="utf-8")

    assert "## Audience jobs" in architecture
    assert "## Disclosure hierarchy" in architecture
    assert "## Front-door CTA invariant" in architecture
    assert map_rows(architecture) == EXPECTED_BLOCKS
    assert "No public CTA; qualified diligence only." in architecture
    assert "exactly these two interactive actions" in architecture

    ctas = re.findall(r"\]\(mailto:[^)]+\)", frontdoor)
    assert len(ctas) == 2, ctas
    assert "front%20door%20%C2%B7%20deploy" in frontdoor
    assert "front%20door%20%C2%B7%20hire" in frontdoor
    assert "Product-operating" not in frontdoor

    print("PASS: PSP-P03-W02 audience and disclosure contract is complete")


if __name__ == "__main__":
    main()
