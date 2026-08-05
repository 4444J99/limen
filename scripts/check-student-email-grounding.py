#!/usr/bin/env python3
"""Predicate for student-email reply grounding doctrine.

The doctrine protects student replies from drifting into instructor-side D2L work:
no reopening, unlocking, date changes, special submission loops, revised-post approval,
or access troubleshooting unless the instructor explicitly asks.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUNDING_DOC = ROOT / "docs" / "student-email-reply-grounding.md"
ENC1101 = ROOT / "organs" / "education" / "engagements" / "enc1101.yaml"

REQUIRED_DOC_PHRASES = [
    "## No Extra Instructor Work",
    "Student email replies must not create extra instructor work",
    "Do not offer to reopen or unlock D2L units",
    "change dates",
    "create special submission workflows",
    "review revised posts",
    "troubleshoot access",
    "I do not reopen closed D2L units",
    "Complete the work and email it when finished",
    "Use that revision to strengthen your own thinking/current essay work",
    "send me a corrected version for approval",
    "consistency, course logistics, and staying focused on current work",
    "Do not reveal private grading/admin reality",
]

REQUIRED_ENC1101_PHRASES = [
    "autonomous D2L window changes",
    "autonomous D2L reopen/unlock/date exceptions",
    "student-email replies that create instructor follow-up work",
    "student-email replies offering revised-post review or approval",
    "D2L window or exception approval",
]

FORBIDDEN_REPLY_EXAMPLE_PHRASES = [
    "reopen the unit",
    "unlock the unit",
    "short window",
    "send me a corrected version",
    "send me a revised version",
    "send it to me for approval",
]

NEGATION_CUES = [
    "do not",
    "don't",
    "not",
    "never",
    "cannot",
    "can't",
    "no ",
    "avoid",
    "without",
]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"FAIL: cannot read {path.relative_to(ROOT)}: {exc}") from exc


def _fenced_code_blocks(text: str) -> list[str]:
    return re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.S)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    return _normalized(phrase) in _normalized(text)


def _has_negation_before(text: str, start: int) -> bool:
    prefix = text[max(0, start - 90):start].lower()
    return any(cue in prefix for cue in NEGATION_CUES)


def main() -> int:
    errors: list[str] = []
    doc_text = _read(GROUNDING_DOC)
    enc1101_text = _read(ENC1101)

    for phrase in REQUIRED_DOC_PHRASES:
        if not _contains_phrase(doc_text, phrase):
            errors.append(f"{GROUNDING_DOC.relative_to(ROOT)} is missing required phrase: {phrase!r}")

    for phrase in REQUIRED_ENC1101_PHRASES:
        if not _contains_phrase(enc1101_text, phrase):
            errors.append(f"{ENC1101.relative_to(ROOT)} is missing required phrase: {phrase!r}")

    for block_index, block in enumerate(_fenced_code_blocks(doc_text), start=1):
        lowered = block.lower()
        for phrase in FORBIDDEN_REPLY_EXAMPLE_PHRASES:
            for match in re.finditer(re.escape(phrase), lowered):
                if not _has_negation_before(lowered, match.start()):
                    errors.append(
                        f"{GROUNDING_DOC.relative_to(ROOT)} code block {block_index} has "
                        f"un-negated labor-creating guidance: {phrase!r}"
                    )

    if errors:
        print("Student-email grounding drift detected:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Student-email grounding doctrine is present and reply examples stay low-labor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
