#!/usr/bin/env python3
"""Focused non-circular regression check for PSP-P03-W04."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLIENT_NARRATIVE = ROOT / "docs/positioning/client-narrative-and-problem-map.md"
FRONTDOOR = ROOT / "docs/positioning/_frontdoor.md"
FLAGSHIP_EVIDENCE = ROOT / "docs/positioning/evidence/flagship-evidence.yaml"
LIMEN_STATUS_URL = "https://limen-dashboard.pages.dev/public-status.json"

REQUIRED_COPY = (
    "**Before state:** An active AI or software initiative can be busy and still be",
    "**Bounded intervention:** A fixed-scope Agentic Delivery Audit examines one",
    "named sponsor, one active initiative, and one decision.",
    "**Expected decision:** The sponsor receives an evidence-linked choice to stop,",
    "keep, narrow, or govern the initiative,",
    "**Exact evidence anchor:**",
    "reported 3,111 total tasks and 1,357 completed tasks on 2026-08-10.",
    "## Problem taxonomy (J-C1 · L2)",
    "## Outcome language (J-C1 · L2)",
    "## Problem-to-proof map (J-C1 · L2)",
    "## CTA copy (J-C1 · L1)",
    "**Client CTA:** Discuss a fixed-scope Agentic Delivery Audit.",
    "## Exclusions and rollback (J-C1 · L2)",
    "## Source boundary (J-C1 · L2)",
)

PROHIBITED_CLAIM_PATTERNS = (
    r"\b(?:price|pricing|fee|rate|discount)\b",
    r"\b(?:customer|customers|adoption|revenue|best[- ]in[- ]the[- ]world|coo|percentile)\b",
    r"[$€£]",
)


def limen_packet(evidence: str) -> str:
    return evidence.split("  - id: limen", 1)[1].split("\n  - id:", 1)[0]


def main() -> None:
    document = CLIENT_NARRATIVE.read_text(encoding="utf-8")
    frontdoor = FRONTDOOR.read_text(encoding="utf-8")
    packet = limen_packet(FLAGSHIP_EVIDENCE.read_text(encoding="utf-8"))

    assert document.startswith("# Client narrative and problem map\n")
    opening = document.split("## Client narrative (J-C1 · L1)\n\n", 1)[1]
    assert opening.startswith(REQUIRED_COPY[0])
    assert "tool" not in opening[:400].lower()
    assert "repository" not in opening[:400].lower()

    for required in REQUIRED_COPY:
        assert required in document, required
    for problem in (
        "Decision-rights gap",
        "Verification gap",
        "Cost-boundary gap",
        "Handoff gap",
    ):
        assert f"| {problem} |" in document, problem

    assert document.count(LIMEN_STATUS_URL) == 5
    assert "mailto:" not in document
    assert document.count("**Client CTA:**") == 1
    for pattern in PROHIBITED_CLAIM_PATTERNS:
        assert not re.search(pattern, document, re.IGNORECASE), pattern

    for required in (
        "status: verified_public_snapshot",
        f"url: {LIMEN_STATUS_URL}",
        "The public dashboard reported 3,111 total tasks on 2026-08-10.",
        "The public dashboard reported 1,357 completed tasks on 2026-08-10.",
        "This packet establishes public operational evidence only;",
        "not claim customer adoption, revenue, or zero-maintenance operation.",
    ):
        assert required in packet, required

    ctas = re.findall(r"\]\(mailto:[^)]+\)", frontdoor)
    assert len(ctas) == 2, ctas
    assert "front%20door%20%C2%B7%20deploy" in frontdoor
    assert "front%20door%20%C2%B7%20hire" in frontdoor

    print("PASS: PSP-P03-W04 client narrative and problem map are complete")


if __name__ == "__main__":
    main()
