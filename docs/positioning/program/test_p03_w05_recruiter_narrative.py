#!/usr/bin/env python3
"""Focused non-circular regression check for PSP-P03-W05."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROLE_MAP = ROOT / "docs/positioning/recruiter-narrative-and-role-map.md"
LIMEN = ROOT / "docs/positioning/evidence/limen.md"
PUBLIC_RECORDS = ROOT / "docs/positioning/evidence/public-records.md"
AI_CHAT_EXPORTER = ROOT / "docs/positioning/evidence/ai-chat-exporter.md"


def section(document: str, heading: str) -> str:
    remainder = document.split(heading, 1)[1]
    return remainder.split("\n## ", 1)[0]


def role_rows(document: str) -> dict[str, tuple[str, str, str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    for line in section(document, "## Role families and exact evidence").splitlines():
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "Role family":
            continue
        assert len(cells) == 4, line
        rows[cells[0]] = (cells[1], cells[2], cells[3])
    return rows


def main() -> None:
    document = ROLE_MAP.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())
    sources = {
        "Staff / Principal systems architecture": (
            " ".join(LIMEN.read_text(encoding="utf-8").split()),
            "governed delivery system",
            "(evidence/limen.md)",
            "governed multi-agent delivery system",
        ),
        "Staff / Principal agent systems architecture": (
            " ".join(LIMEN.read_text(encoding="utf-8").split()),
            "multi-agent delivery system",
            "(evidence/limen.md)",
            "operating, failure, and verification receipts",
        ),
        "Staff / Principal data systems architecture": (
            " ".join(PUBLIC_RECORDS.read_text(encoding="utf-8").split()),
            "multi-stage public-record decision pipeline",
            "(evidence/public-records.md)",
            "Four implemented state collectors (CA, TX, FL, and NY)",
        ),
        "Senior product systems engineering": (
            " ".join(AI_CHAT_EXPORTER.read_text(encoding="utf-8").split()),
            "client-side conversation export tool",
            "(evidence/ai-chat-exporter.md)",
            "five export formats: Markdown, HTML, JSON, PNG, and text",
        ),
    }

    for heading in (
        "## Recruiter summary",
        "## Public-source resume spine",
        "## Interview proof map",
        "## Explicit limitations",
        "## Partnership gate",
        "## Rollback",
    ):
        assert heading in document, heading

    rows = role_rows(document)
    assert set(rows) == set(sources), rows
    for role, (scope, evidence, boundary) in rows.items():
        source, scope_fragment, link, source_fragment = sources[role]
        assert scope_fragment in scope, role
        assert link in evidence, role
        assert source_fragment in source, role
        assert any(term in boundary.lower() for term in ("does not", "do not")), role

    for forbidden in (
        "coo",
        "caio",
        "executive standing",
        "best-in-world",
        "percentile",
    ):
        assert forbidden not in document.lower(), forbidden

    assert "Issue #1429 remains open" in normalized_document
    assert "current resume PDF or text has not been reviewed" in normalized_document
    assert "Product-operating partnership remains gated at L3." in normalized_document
    assert "HG-OPERATOR-TERMS" in normalized_document
    assert "third public CTA" in normalized_document
    assert "does not draft or evaluate W06 messaging" in normalized_document
    print("PASS: PSP-P03-W05 recruiter narrative maps all role families to independent public evidence")


if __name__ == "__main__":
    main()
