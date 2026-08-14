#!/usr/bin/env python3
"""Fail-closed validator for the PSP-P03-W07 blinded-reader evidence set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, SchemaError


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "docs/positioning/program"
PROTOCOL = ROOT / "docs/positioning/w07-blinded-reader-protocol.md"
SCHEMA = PROGRAM / "w07_blinded_reader_response_schema.json"
DEFAULT_RESPONSES = PROGRAM / "w07_blinded_reader_response_template.json"

SCHEMA_VERSION = "psp-p03-w07-reader-set.v2"
WORK_ID = "PSP-P03-W07"
STIMULUS = {
    "repository": "organvm/limen",
    "head": "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
    "reader_block_sha256": "d2f95a2b2ee6d1b2f7a924125eb65e5045613ff7d7c38654b2e0503c57edd8b7",
    "issue_comment": "https://github.com/organvm/limen/issues/2188#issuecomment-5271321054",
}
READER_SLOTS = (
    ("R1", "client"),
    ("R2", "internal_evaluator"),
    ("R3", "recruiter"),
    ("R4", "executive_sponsor"),
    ("R5", "product_partner"),
)
ARCHETYPES = {
    "client",
    "internal_evaluator",
    "recruiter",
    "executive_sponsor",
    "product_partner",
}
ANSWER_FIELDS = (
    "role_identified",
    "buyer_identified",
    "problem_identified",
    "proof_identified",
    "cta_identified",
)
SCORE_FIELDS = ("role", "buyer", "problem", "proof", "cta")
INTEGRITY_FIELDS = (
    "independent_target_like_reader",
    "genuine_human_response",
    "not_model_or_synthetic",
    "not_author_or_implementation_agent",
    "not_coached",
    "read_once_unprompted",
    "no_facilitator_explanation",
    "no_project_search",
    "contains_no_names_companies_or_contact_data",
)
OBJECTION_CATEGORIES = {
    "role_confusion",
    "buyer_confusion",
    "proof_skepticism",
    "cta_ambiguity",
    "authority_takeover_concern",
    "detail_density_concern",
    "unrelated",
}
ROOT_KEYS = {"schema_version", "work_id", "stimulus", "status", "collected_at", "readers"}
READER_KEYS = {
    "reader_id",
    "archetype",
    *ANSWER_FIELDS,
    "confidence_1_to_5",
    "confusions",
    "trust_objections",
    "verbatim_notes",
    "element_scores",
    "protocol_integrity",
}
PII_PATTERNS = (
    ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("URL", re.compile(r"https?://|www\.", re.IGNORECASE)),
    ("account handle", re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,}")),
    ("phone or long identifier", re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){7,}\d(?!\d)")),
    ("IPv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("government identifier", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("named company suffix", re.compile(r"\b(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Corporation|GmbH|PLC)\b", re.IGNORECASE)),
    ("titled personal name", re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]{1,}\b")),
    (
        "postal address",
        re.compile(
            r"\b\d{1,6}\s+(?:[A-Za-z0-9.-]+\s+){0,4}"
            r"(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b",
            re.IGNORECASE,
        ),
    ),
)


class EvidenceError(ValueError):
    """Raised when a response set violates the intake contract."""


@dataclass(frozen=True)
class Verdict:
    state: str
    message: str
    total: int = 0
    role_hits: int = 0
    buyer_hits: int = 0
    cta_hits: int = 0


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read response set: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvidenceError("response set must be a JSON object")
    return payload


def schema_payload() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
        Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as exc:
        raise EvidenceError(f"cannot load tracked JSON schema: {exc}") from exc
    if not isinstance(schema, dict):
        raise EvidenceError("tracked JSON schema must be an object")
    return schema


def _validate_schema(payload: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(schema_payload()).iter_errors(payload),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise EvidenceError(f"JSON schema violation at {location}: {error.message}")


def _reader_block_digest() -> str:
    try:
        document = PROTOCOL.read_text(encoding="utf-8")
        block = document.split("<!-- READER BLOCK START -->", 1)[1].split("<!-- READER BLOCK END -->", 1)[0]
    except (OSError, UnicodeError, IndexError) as exc:
        raise EvidenceError(f"cannot resolve the tracked reader stimulus: {exc}") from exc
    canonical = block.strip() + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise EvidenceError(
            f"{label} keys differ: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    return value


def _text(value: Any, label: str, *, maximum: int, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise EvidenceError(f"{label} must be a string")
    if len(value) > maximum:
        raise EvidenceError(f"{label} exceeds {maximum} characters")
    if not allow_empty and not value.strip():
        raise EvidenceError(f"{label} must not be empty")
    for kind, pattern in PII_PATTERNS:
        if pattern.search(value):
            raise EvidenceError(f"{label} contains prohibited {kind} data")
    return value


def _string_list(value: Any, label: str, *, allow_empty_values: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > 10:
        raise EvidenceError(f"{label} must be an array of at most 10 strings")
    return [
        _text(item, f"{label}[{index}]", maximum=500, allow_empty=allow_empty_values)
        for index, item in enumerate(value)
    ]


def _rfc3339(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError("collected_at must be an RFC3339 UTC timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("collected_at must be an RFC3339 UTC timestamp") from exc


def _normalize_objection(category: str) -> str:
    # Category-level aggregation is deliberately conservative: three readers
    # independently raising the same class is structural even when wording differs.
    return category


def validate(payload: dict[str, Any]) -> Verdict:
    _validate_schema(payload)
    if _reader_block_digest() != STIMULUS["reader_block_sha256"]:
        raise EvidenceError("tracked reader stimulus digest does not match the accepted copy")
    root = _exact_keys(payload, ROOT_KEYS, "response set")
    if root["schema_version"] != SCHEMA_VERSION:
        raise EvidenceError("schema_version does not match the W07 contract")
    if root["work_id"] != WORK_ID:
        raise EvidenceError("work_id does not match PSP-P03-W07")
    if root["stimulus"] != STIMULUS:
        raise EvidenceError("stimulus identity does not match the accepted W01-W06 head")
    if root["status"] not in {"pending", "complete"}:
        raise EvidenceError("status must be pending or complete")
    pending = root["status"] == "pending"
    if pending:
        if root["collected_at"] is not None:
            raise EvidenceError("pending response set must not claim a collection timestamp")
    else:
        _rfc3339(root["collected_at"])

    readers = root["readers"]
    if not isinstance(readers, list) or len(readers) != 5:
        raise EvidenceError("response set must contain exactly five reader records")

    reader_ids: list[str] = []
    archetypes: list[str] = []
    score_totals = Counter({field: 0 for field in SCORE_FIELDS})
    repeated_objections: Counter[str] = Counter()
    authority_unresolved = False

    for index, raw_reader in enumerate(readers):
        label = f"readers[{index}]"
        reader = _exact_keys(raw_reader, READER_KEYS, label)
        reader_id = reader["reader_id"]
        expected_reader_id, expected_archetype = READER_SLOTS[index]
        if reader_id != expected_reader_id:
            raise EvidenceError(f"{label}.reader_id must be {expected_reader_id}")
        reader_ids.append(reader_id)
        archetype = reader["archetype"]
        if archetype != expected_archetype:
            raise EvidenceError(f"{label}.archetype must be {expected_archetype}")
        archetypes.append(archetype)

        for field in ANSWER_FIELDS:
            _text(reader[field], f"{label}.{field}", maximum=1000, allow_empty=pending)
        confidence = reader["confidence_1_to_5"]
        if isinstance(confidence, bool) or not isinstance(confidence, int):
            raise EvidenceError(f"{label}.confidence_1_to_5 must be an integer")
        if pending and confidence != 0:
            raise EvidenceError(f"{label}.confidence_1_to_5 must be 0 while pending")
        if not pending and not 1 <= confidence <= 5:
            raise EvidenceError(f"{label}.confidence_1_to_5 must be between 1 and 5")
        _string_list(reader["confusions"], f"{label}.confusions")
        _text(reader["verbatim_notes"], f"{label}.verbatim_notes", maximum=2000, allow_empty=True)

        objections = reader["trust_objections"]
        if not isinstance(objections, list) or len(objections) > 10:
            raise EvidenceError(f"{label}.trust_objections must be an array of at most 10 objects")
        seen_for_reader: set[str] = set()
        for objection_index, raw_objection in enumerate(objections):
            objection_label = f"{label}.trust_objections[{objection_index}]"
            objection = _exact_keys(raw_objection, {"category", "summary", "unresolved"}, objection_label)
            category = objection["category"]
            if category not in OBJECTION_CATEGORIES:
                raise EvidenceError(f"{objection_label}.category is not accepted")
            _text(
                objection["summary"],
                f"{objection_label}.summary",
                maximum=500,
                allow_empty=False,
            )
            unresolved = objection["unresolved"]
            if not isinstance(unresolved, bool):
                raise EvidenceError(f"{objection_label}.unresolved must be boolean")
            key = _normalize_objection(category)
            seen_for_reader.add(key)
            if category == "authority_takeover_concern" and unresolved:
                authority_unresolved = True
        repeated_objections.update(seen_for_reader)

        scores = _exact_keys(reader["element_scores"], set(SCORE_FIELDS), f"{label}.element_scores")
        for field in SCORE_FIELDS:
            if not isinstance(scores[field], bool):
                raise EvidenceError(f"{label}.element_scores.{field} must be boolean")
            score_totals[field] += int(scores[field])

        integrity = _exact_keys(reader["protocol_integrity"], set(INTEGRITY_FIELDS), f"{label}.protocol_integrity")
        for field in INTEGRITY_FIELDS:
            if not isinstance(integrity[field], bool):
                raise EvidenceError(f"{label}.protocol_integrity.{field} must be boolean")
            if not pending and not integrity[field]:
                raise EvidenceError(f"{label} fails protocol integrity: {field}")
        if pending:
            has_content = (
                any(reader[field] for field in ANSWER_FIELDS)
                or reader["confusions"]
                or reader["trust_objections"]
                or reader["verbatim_notes"]
                or confidence != 0
                or any(scores.values())
                or any(integrity.values())
            )
            if has_content:
                raise EvidenceError(f"{label} pending record must remain an empty initialization slot")

    if set(reader_ids) != {"R1", "R2", "R3", "R4", "R5"} or len(set(reader_ids)) != 5:
        raise EvidenceError("reader IDs must be exactly R1 through R5 with no duplicates")
    if set(archetypes) != ARCHETYPES or len(set(archetypes)) != 5:
        raise EvidenceError("reader archetypes must occupy each of the five slots exactly once")

    if pending:
        return Verdict("blocked", "PSP-P03-W07 pending five independent collected reader records")

    total = sum(score_totals.values())
    repeated = sorted(key for key, count in repeated_objections.items() if count >= 3)
    blockers: list[str] = []
    if total < 20:
        blockers.append(f"total score {total}/25 is below 20")
    if score_totals["role"] < 4:
        blockers.append(f"role identifications {score_totals['role']}/5 are below 4")
    if score_totals["buyer"] < 4:
        blockers.append(f"buyer identifications {score_totals['buyer']}/5 are below 4")
    if score_totals["cta"] < 4:
        blockers.append(f"CTA identifications {score_totals['cta']}/5 are below 4")
    if authority_unresolved:
        blockers.append("an authority/takeover objection remains unresolved")
    if repeated:
        blockers.append("structural objection categories repeated by at least three readers: " + ", ".join(repeated))
    if blockers:
        return Verdict(
            "blocked",
            "; ".join(blockers),
            total,
            score_totals["role"],
            score_totals["buyer"],
            score_totals["cta"],
        )
    return Verdict(
        "pass",
        "PSP-P03-W07 blinded-reader intake meets deterministic thresholds",
        total,
        score_totals["role"],
        score_totals["buyer"],
        score_totals["cta"],
    )


def render_verdict(verdict: Verdict) -> str:
    if verdict.state == "blocked":
        return f"BLOCKED: {verdict.message}"
    return (
        f"PASS: {verdict.message}\n"
        f"SCORE: total={verdict.total}/25 role={verdict.role_hits}/5 "
        f"buyer={verdict.buyer_hits}/5 cta={verdict.cta_hits}/5"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", nargs="?", type=Path, default=DEFAULT_RESPONSES)
    args = parser.parse_args(argv)
    try:
        verdict = validate(load_payload(args.responses))
    except EvidenceError as exc:
        print(f"FAIL: PSP-P03-W07 invalid blinded-reader evidence: {exc}")
        return 1
    print(render_verdict(verdict))
    return 2 if verdict.state == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
