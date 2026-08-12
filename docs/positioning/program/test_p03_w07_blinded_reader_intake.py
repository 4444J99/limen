#!/usr/bin/env python3
"""Focused tests for the PSP-P03-W07 blinded-reader intake package."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "docs/positioning/program"
PROTOCOL = ROOT / "docs/positioning/w07-blinded-reader-protocol.md"
SCHEMA = PROGRAM / "w07_blinded_reader_response_schema.json"
TEMPLATE = PROGRAM / "w07_blinded_reader_response_template.json"
VALIDATOR = PROGRAM / "validate_p03_w07_blinded_reader.py"

SPEC = importlib.util.spec_from_file_location("validate_p03_w07_blinded_reader", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def passing_payload() -> dict:
    payload = template()
    payload["status"] = "complete"
    payload["collected_at"] = "2026-08-12T20:00:00Z"
    for reader in payload["readers"]:
        reader.update(
            {
                "role_identified": "A senior production-systems architect with bounded authority.",
                "buyer_identified": "A named technical or executive sponsor with an active mandate.",
                "problem_identified": "Delivery lacks decision rights, verification, cost bounds, and handoff.",
                "proof_identified": "An inspectable governed-delivery system with operating evidence.",
                "cta_identified": "Discuss the bounded audit or a named senior systems mandate.",
                "confidence_1_to_5": 5,
                "element_scores": {"role": True, "buyer": True, "problem": True, "proof": True, "cta": True},
                "protocol_integrity": {field: True for field in MODULE.INTEGRITY_FIELDS},
            }
        )
    return payload


def test_protocol_preserves_exact_copy_ready_stimulus_and_questions() -> None:
    document = PROTOCOL.read_text(encoding="utf-8")
    reader_block = document.split("<!-- READER BLOCK START -->", 1)[1].split("<!-- READER BLOCK END -->", 1)[0]
    for fragment in (
        "I build production systems that solve expensive problems.",
        "A written mandate defines authority",
        "fixed-scope Agentic Delivery Audit",
        "What role or identity do you think this person is presenting?",
        "What should the next action be after reading this?",
    ):
        assert fragment in reader_block
    for leaked_term in ("PSP-P03-W07", "W06", "intended interpretation", "scoring"):
        assert leaked_term not in reader_block


def test_schema_is_strict_and_requires_exactly_five_records() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    readers = schema["properties"]["readers"]
    assert readers["minItems"] == readers["maxItems"] == 5
    assert readers["items"]["additionalProperties"] is False
    assert set(readers["items"]["required"]) == MODULE.READER_KEYS
    assert schema["properties"]["schema_version"]["const"] == MODULE.SCHEMA_VERSION
    assert (
        schema["properties"]["stimulus"]["properties"]["reader_block_sha256"]["const"]
        == MODULE.STIMULUS["reader_block_sha256"]
    )
    assert set(readers["items"]["properties"]["protocol_integrity"]["required"]) == set(MODULE.INTEGRITY_FIELDS)


def test_tracked_template_is_pending_and_fails_closed() -> None:
    payload = template()
    assert len(payload["readers"]) == 5
    verdict = MODULE.validate(payload)
    assert verdict.state == "blocked"
    assert verdict.message == "PSP-P03-W07 pending five independent collected reader records"


def test_synthetic_in_test_threshold_fixture_passes() -> None:
    verdict = MODULE.validate(passing_payload())
    assert verdict.state == "pass"
    assert verdict.total == 25
    assert (verdict.role_hits, verdict.buyer_hits, verdict.cta_hits) == (5, 5, 5)


def test_numeric_threshold_failure_stays_blocked() -> None:
    payload = passing_payload()
    for reader in payload["readers"][:2]:
        reader["element_scores"]["role"] = False
        reader["element_scores"]["buyer"] = False
        reader["element_scores"]["cta"] = False
    verdict = MODULE.validate(payload)
    assert verdict.state == "blocked"
    assert "below 20" in verdict.message
    assert "role identifications 3/5 are below 4" in verdict.message


def test_repeated_objection_is_structural_even_when_numeric_score_passes() -> None:
    payload = passing_payload()
    summaries = (
        "The proof feels too internal.",
        "I cannot tell whether the evidence transfers.",
        "The example does not establish an outside result.",
    )
    for reader, summary in zip(payload["readers"][:3], summaries, strict=True):
        reader["trust_objections"] = [{"category": "proof_skepticism", "summary": summary, "unresolved": False}]
    verdict = MODULE.validate(payload)
    assert verdict.state == "blocked"
    assert "structural objection" in verdict.message
    assert "proof_skepticism" in verdict.message


def test_unresolved_authority_objection_blocks() -> None:
    payload = passing_payload()
    payload["readers"][0]["trust_objections"] = [
        {
            "category": "authority_takeover_concern",
            "summary": "The mandate could displace current owners.",
            "unresolved": True,
        }
    ]
    verdict = MODULE.validate(payload)
    assert verdict.state == "blocked"
    assert "authority/takeover" in verdict.message


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["readers"][1].update(reader_id="R1"),
        lambda payload: payload["readers"][1].update(archetype="client"),
        lambda payload: payload["readers"][0].update(extra_private_field="forbidden"),
        lambda payload: payload["readers"][0].update(verbatim_notes="reader@example.com"),
        lambda payload: payload["readers"][0]["protocol_integrity"].update(no_project_search=False),
    ],
)
def test_invalid_or_non_blind_evidence_fails_closed(mutate) -> None:
    payload = copy.deepcopy(passing_payload())
    mutate(payload)
    with pytest.raises(MODULE.EvidenceError):
        MODULE.validate(payload)
