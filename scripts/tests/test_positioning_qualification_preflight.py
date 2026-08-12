from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "positioning-qualification-preflight.py"
MANIFEST = ROOT / "docs" / "positioning" / "sales" / "psp-c09" / "icp-and-buying-signals.preflight.json"
SPEC = importlib.util.spec_from_file_location("positioning_qualification_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_live_source_heads_assignments_and_ten_synthetic_accounts_are_valid() -> None:
    data = load_manifest()
    assert MODULE.validate(data) == []
    assert len(data["syntheticAccounts"]) == 10
    assert data["assignments"] == MODULE.EXPECTED_ASSIGNMENTS
    assert data["sourceLock"] == MODULE.EXPECTED_SOURCE_LOCK
    assert data["upstreamState"] == MODULE.EXPECTED_UPSTREAM_STATE


def test_each_synthetic_account_scores_and_routes_deterministically() -> None:
    data = load_manifest()
    scorecard = data["scorecard"]
    observed = {
        account["id"]: (
            MODULE.score_account(account, scorecard),
            MODULE.disposition(account, scorecard),
        )
        for account in data["syntheticAccounts"]
    }
    assert set(route for _, route in observed.values()) == {
        "qualified_audit",
        "one_bounded_follow_up",
        "decline",
    }
    for account in data["syntheticAccounts"]:
        assert observed[account["id"]] == (
            account["expectedScore"],
            account["expectedDisposition"],
        )


def test_disqualifier_overrides_a_perfect_score() -> None:
    data = load_manifest()
    account = copy.deepcopy(data["syntheticAccounts"][0])
    account["hardDisqualifiers"] = ["security_or_approval_bypass"]
    assert MODULE.score_account(account, data["scorecard"]) == 10
    assert MODULE.disposition(account, data["scorecard"]) == "decline"


def test_missing_required_evidence_cannot_be_laundered_by_total_score() -> None:
    data = load_manifest()
    account = copy.deepcopy(data["syntheticAccounts"][0])
    account["facts"]["read_only_evidence"] = False
    assert MODULE.score_account(account, data["scorecard"]) == 9
    assert MODULE.disposition(account, data["scorecard"]) == "one_bounded_follow_up"


def test_real_contact_or_commercial_outcome_fields_fail_closed() -> None:
    data = load_manifest()
    data["syntheticAccounts"][0]["contactEmail"] = "nobody@example.invalid"
    failures = MODULE.validate(data)
    assert any("real-contact/commercial outcome keys prohibited" in failure for failure in failures)


def test_formal_or_effectful_state_fails_closed() -> None:
    data = load_manifest()
    data["formalPredicateRun"] = True
    data["externalEffects"] = ["synthetic_send_misrepresented"]
    failures = MODULE.validate(data)
    assert "formal work must remain open" in failures
    assert "preflight must remain synthetic and effect-free" in failures


def test_reader_or_prepared_dependency_promotion_fails_closed() -> None:
    data = load_manifest()
    data["upstreamState"]["c03ReaderEvidenceSatisfied"] = True
    data["upstreamState"]["c08State"] = "closed"
    failures = MODULE.validate(data)
    assert "upstream state must preserve the accepted/open/prepared boundary" in failures


def test_source_lock_requires_current_public_and_private_receipts() -> None:
    data = load_manifest()
    data["sourceLock"]["deliveryOsRelay"] = "organvm/limen#2315@stale"
    failures = MODULE.validate(data)
    assert "source lock drifted from exact upstream heads" in failures
