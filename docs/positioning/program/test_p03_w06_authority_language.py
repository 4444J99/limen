#!/usr/bin/env python3
"""Focused non-circular rubric check for PSP-P03-W06."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LANGUAGE = ROOT / "docs/positioning/authority-and-trust-language.md"

POSITIVE_SIGNALS = (
    "additive leverage",
    "sponsor-granted scope",
    "written mandate",
    "collaboration",
    "reversible work",
    "roll it back",
    "current-owner visibility",
    "clean handoff",
    "only the access needed",
    "ask before",
    "evidence",
    "acceptance condition",
)

DEFECTS = (
    "take over",
    "own the organization",
    "bypass approval",
    "just trust me",
    "don't worry",
    "no questions asked",
    "surveil",
    "spy on",
    "monitor everybody",
    "replace leadership",
    "executive substitute",
)


def section(document: str, heading: str, next_heading: str) -> str:
    return document.split(heading, 1)[1].split(next_heading, 1)[0]


def main() -> None:
    document = LANGUAGE.read_text(encoding="utf-8")
    normalized = " ".join(document.lower().split())
    answers = section(
        document,
        "## Authority and answer library",
        "## Language guardrails",
    ).lower()

    for heading in (
        "## Core authority boundary",
        "## Threat triggers and evidence-first reframes",
        "## Authority and answer library",
        "## Language guardrails",
        "## Deterministic scoring rubric",
        "## Rollback",
    ):
        assert heading in document, heading

    for trigger in (
        "Control-loss fear",
        "Access and custody fear",
        "Irreversibility fear",
        "Role-displacement fear",
        "Motivation-conflict fear",
        "Status threat",
    ):
        assert trigger in document, trigger

    for prompt in (
        "### How does your work fit with existing leadership?",
        "### What authority are you asking for?",
        "### How will you use access?",
        "### How do you work with the team?",
        "### What happens if the proposed change is wrong?",
        "### What remains after the work ends?",
        "### Are you proposing a new executive layer?",
        "### Why should a client or hiring team trust the scope?",
    ):
        assert prompt in document, prompt

    positive_score = sum(signal in answers for signal in POSITIVE_SIGNALS)
    defects = [defect for defect in DEFECTS if defect in answers]
    score = positive_score - (5 * len(defects))

    assert positive_score == len(POSITIVE_SIGNALS), positive_score
    assert defects == [], defects
    assert score >= 8, score
    assert "reviewers score" not in normalized
    assert "w07 owns target-reader review" in normalized

    print("PASS: PSP-P03-W06 authority language clears deterministic collaboration rubric")


if __name__ == "__main__":
    main()
