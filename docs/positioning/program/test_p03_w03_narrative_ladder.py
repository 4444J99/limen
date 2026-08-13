#!/usr/bin/env python3
"""Focused non-circular comprehension check for PSP-P03-W03."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LADDER = ROOT / "docs/positioning/narrative-ladder.md"
FRONTDOOR = ROOT / "docs/positioning/_frontdoor.md"


def section(document: str, heading: str) -> str:
    remainder = document.split(heading, 1)[1]
    return remainder.split("\n## ", 1)[0]


def main() -> None:
    document = LADDER.read_text(encoding="utf-8")
    frontdoor = FRONTDOOR.read_text(encoding="utf-8")

    l1 = " ".join(section(document, "## L1 — ten seconds").split())
    for required in (
        "Production-systems architect.",
        "I build production systems that solve expensive problems.",
        "For a direct client,",
        "For a recruiter or hiring executive,",
        "The expensive problem is",
        "Strongest proof: Limen.",
        "**Client CTA:** Discuss a fixed-scope Agentic Delivery Audit.",
        "**Recruiter CTA:** Discuss a senior systems architecture or engineering role",
    ):
        assert required in l1, required
    assert l1.count(" CTA:**") == 2
    assert "Product-operating partnership is not a front-door path." in l1

    l2 = " ".join(section(document, "## L2 — five minutes").split())
    for required in (
        "decision rights",
        "verified done",
        "Limen is the method proof",
        "UCC Public-Records Intelligence Platform",
        "four implemented state collectors",
        "AI Chat Exporter",
        "five export formats",
        "not a claim about customer deployment, adoption, revenue, or zero maintenance",
    ):
        assert required in l2, required

    l3 = " ".join(section(document, "## L3 — diligence index").split())
    for required in (
        "Claim register and source links",
        "Scope and authority",
        "Acceptance and handoff",
        "No public price",
        "Product-operating partnership",
        "gated L3 only",
        "HG-OPERATOR-TERMS",
        "diligence access grants no operating authority",
    ):
        assert required in l3, required

    ctas = re.findall(r"\]\(mailto:[^)]+\)", frontdoor)
    assert len(ctas) == 2, ctas
    assert "front%20door%20%C2%B7%20deploy" in frontdoor
    assert "front%20door%20%C2%B7%20hire" in frontdoor
    assert "Product-operating" not in frontdoor

    print("PASS: PSP-P03-W03 narrative ladder is complete and comprehensible")


if __name__ == "__main__":
    main()
