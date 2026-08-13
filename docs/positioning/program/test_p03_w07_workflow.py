#!/usr/bin/env python3
"""Focused tests for the complete PSP-P03-W07 reversible workflow."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "docs/positioning/program"
VALIDATOR_PATH = PROGRAM / "validate_p03_w07_blinded_reader.py"
WORKFLOW_PATH = PROGRAM / "w07_blinded_reader_workflow.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


V = load_module("w07_validator_for_workflow_test", VALIDATOR_PATH)
W = load_module("w07_workflow_for_test", WORKFLOW_PATH)


def passing_payload() -> dict:
    payload = V.load_payload(V.DEFAULT_RESPONSES)
    payload["status"] = "complete"
    payload["collected_at"] = "2026-08-12T20:00:00Z"
    for reader in payload["readers"]:
        reader.update(
            {
                "role_identified": "Production-systems architect.",
                "buyer_identified": "A technical or executive sponsor.",
                "problem_identified": "Ungoverned delivery decisions and handoff.",
                "proof_identified": "Inspectable Limen operating evidence.",
                "cta_identified": "Discuss the bounded audit or a named role.",
                "confidence_1_to_5": 5,
                "element_scores": {field: True for field in V.SCORE_FIELDS},
                "protocol_integrity": {field: True for field in V.INTEGRITY_FIELDS},
            }
        )
    return payload


def raw_import(payload: dict) -> dict:
    return {
        "schema_version": W.IMPORT_SCHEMA_VERSION,
        "collected_at": payload["collected_at"],
        "readers": copy.deepcopy(payload["readers"]),
    }


def test_initialization_is_deterministic_and_contains_no_claimed_readers() -> None:
    first = W.initialization_payload()
    second = W.initialization_payload()
    assert first == second
    assert first["collected_at"] is None
    assert len(first["readers"]) == 5
    assert all(not any(reader["protocol_integrity"].values()) for reader in first["readers"])


def test_import_injects_immutable_stimulus_and_applies_schema() -> None:
    payload, verdict = W.import_response_set(raw_import(passing_payload()))
    assert verdict.state == "pass"
    assert payload["work_id"] == V.WORK_ID
    assert payload["stimulus"] == V.STIMULUS
    assert payload["schema_version"] == V.SCHEMA_VERSION


@pytest.mark.parametrize(
    "field",
    (
        "genuine_human_response",
        "not_model_or_synthetic",
        "not_author_or_implementation_agent",
        "not_coached",
    ),
)
def test_model_author_coached_or_synthetic_records_never_count(field: str) -> None:
    raw = raw_import(passing_payload())
    raw["readers"][0]["protocol_integrity"][field] = False
    with pytest.raises(V.EvidenceError):
        W.import_response_set(raw)


@pytest.mark.parametrize(
    "value",
    (
        "reader@example.com",
        "https://example.com/profile",
        "@reader_handle",
        "+1 (212) 555-0100",
        "192.0.2.4",
        "Reader Works LLC",
        "Dr Jane",
        "10 Main Street",
    ),
)
def test_strict_pii_patterns_are_rejected(value: str) -> None:
    raw = raw_import(passing_payload())
    raw["readers"][0]["verbatim_notes"] = value
    with pytest.raises(V.EvidenceError, match="prohibited"):
        W.import_response_set(raw)


def test_json_schema_validation_runs_before_semantic_scoring() -> None:
    payload = passing_payload()
    payload["readers"][0]["confidence_1_to_5"] = "5"
    with pytest.raises(V.EvidenceError, match="JSON schema violation"):
        V.validate(payload)


def test_category_level_repetition_is_structural_across_different_words() -> None:
    payload = passing_payload()
    summaries = (
        "The proof is internal.",
        "The evidence may not transfer.",
        "I need an outside result.",
    )
    for reader, summary in zip(payload["readers"][:3], summaries, strict=True):
        reader["trust_objections"] = [
            {
                "category": "proof_skepticism",
                "summary": summary,
                "unresolved": False,
            }
        ]
    verdict = V.validate(payload)
    assert verdict.state == "blocked"
    assert "proof_skepticism" in verdict.message


def test_decision_memo_is_aggregate_only() -> None:
    payload = passing_payload()
    payload["readers"][0]["verbatim_notes"] = "unique private-style phrase"
    verdict = V.validate(payload)
    memo = W.decision_memo(payload, verdict)
    assert "unique private-style phrase" not in memo
    assert W.response_sha256(payload) in memo
    assert "Total: 25/25" in memo


def test_receipt_candidate_is_bound_to_stimulus_head_and_exact_output_hash() -> None:
    payload = passing_payload()
    verdict = V.validate(payload)
    observed_head = "f" * 40
    response_path = "docs/receipts/positioning/psp-p03-w07-reader-responses.json"
    memo_path = "docs/receipts/positioning/psp-p03-w07-decision-memo.md"
    comment = W.build_receipt_comment(
        payload,
        verdict,
        observed_head=observed_head,
        observed_at="2026-08-12T21:00:00Z",
        acceptance_sha256="a" * 64,
        changed_paths=[response_path, memo_path],
        response_path=response_path,
        memo_path=memo_path,
    )
    fence = chr(96) * 3
    receipt = json.loads(comment.split(f"{fence}json\n", 1)[1].split(f"\n{fence}", 1)[0])
    expected_output = V.render_verdict(verdict) + "\n"
    assert receipt["observed_heads"] == {"organvm/limen": observed_head}
    assert receipt["predicate"]["output_sha256"] == hashlib.sha256(expected_output.encode("utf-8")).hexdigest()
    assert V.STIMULUS["issue_comment"] in receipt["evidence_urls"]
    assert all(observed_head in url for url in receipt["evidence_urls"][-2:])


def test_receipt_candidate_refuses_below_threshold_evidence() -> None:
    payload = passing_payload()
    payload["readers"][0]["element_scores"] = {field: False for field in V.SCORE_FIELDS}
    payload["readers"][1]["element_scores"] = {field: False for field in V.SCORE_FIELDS}
    verdict = V.validate(payload)
    assert verdict.state == "blocked"
    with pytest.raises(W.WorkflowError, match="passing five-reader verdict"):
        W.build_receipt_comment(
            payload,
            verdict,
            observed_head="f" * 40,
            observed_at="2026-08-12T21:00:00Z",
            acceptance_sha256="a" * 64,
            changed_paths=[],
            response_path="responses.json",
            memo_path="memo.md",
        )


def test_write_exact_is_idempotent_but_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "candidate.json"
    W._write_exact(output, "one\n")
    W._write_exact(output, "one\n")
    with pytest.raises(W.WorkflowError, match="refusing to overwrite"):
        W._write_exact(output, "two\n")
