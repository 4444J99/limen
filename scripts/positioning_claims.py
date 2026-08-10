#!/usr/bin/env python3
"""Claim-contract checks shared by public positioning renderers.

The canonical policy is ``docs/positioning/claims-ledger.md``. This module
protects the public render boundary: a renderer must refuse the ledger's
prohibited claim classes rather than silently publishing them.
"""

from __future__ import annotations

import re


# Each expression names a ledger rule rather than trying to infer truth from
# wording. Evidence-labelled, permitted facts remain the responsibility of the
# renderer that supplies their status label.
FORBIDDEN_PUBLIC_CLAIMS: dict[str, re.Pattern[str]] = {
    "unreproducible-ranking": re.compile(r"\btop\s+(?:0\.1|1)\s*%", re.IGNORECASE),
    "unsupported-product-count": re.compile(
        r"(?:~|about|over)?\s*100\s+(?:shipped|functioning)\s+products", re.IGNORECASE
    ),
    "manual-only-authorship": re.compile(r"\bsolo[- ]built\b", re.IGNORECASE),
    "unsupported-daily-adoption": re.compile(
        r"\bthousands\s+of\s+(?:people|users).{0,40}\b(?:daily|every day)\b", re.IGNORECASE
    ),
    "unsupported-commercial-proof": re.compile(
        r"\b(?:paying customers?|customer adoption|external adoption|revenue|mrr)\b"
        r"(?!(?:[^\n.]{0,50})\b(?:unverified|unvalidated|modest\s+and\s+directly\s+observable)\b)",
        re.IGNORECASE,
    ),
    "unsupported-executive-title": re.compile(r"\b(?:coo-level|fractional[- ]caio|\bcaio\b)\b", re.IGNORECASE),
    "unsupported-implemented-coverage": re.compile(
        r"\b(?:production\s+)?50-state\s+(?:ucc\s+)?(?:platform|aggregation)\b", re.IGNORECASE
    ),
    "unsupported-live-deployment": re.compile(r"\blive\s+vercel\s+deploy(?:ment)?\b", re.IGNORECASE),
    "unsupported-collection-scale": re.compile(r"\b60\+\s+collection\s+agents\b", re.IGNORECASE),
    "unsupported-lead-delivery": re.compile(
        r"\bwe\s+deliver\s+(?:scored,?\s+enriched,?\s+)?exclusive\s+ucc\s+leads\b", re.IGNORECASE
    ),
    "unsupported-employment-outcome": re.compile(
        r"\b(?:people\s+(?:are\s+)?(?:already\s+)?knocking|"
        r"come\s+run\s+(?:our|your)\s+data\s+org)\b",
        re.IGNORECASE,
    ),
}


def public_claim_violations(text: str) -> list[str]:
    """Return stable rule identifiers for prohibited claims found in ``text``."""
    return [rule for rule, pattern in FORBIDDEN_PUBLIC_CLAIMS.items() if pattern.search(text)]


def assert_public_claims(text: str, surface: str) -> None:
    """Fail closed when a public renderer would emit an unsupported claim."""
    violations = public_claim_violations(text)
    if violations:
        joined = ", ".join(violations)
        raise ValueError(
            f"refusing to emit public positioning for {surface}: "
            f"claims ledger forbids {joined}"
        )
