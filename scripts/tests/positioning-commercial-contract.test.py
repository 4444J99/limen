#!/usr/bin/env python3
"""Hermetic regression tests for the PSP-C03 commercial contract."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/positioning-commercial-contract.py"
SPEC = importlib.util.spec_from_file_location("positioning_commercial_contract", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CommercialContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_contract()

    def errors(self, contract=None) -> list[str]:
        return MODULE.validate_contract(contract or self.contract)

    def assert_has_error(self, contract, phrase: str) -> None:
        errors = self.errors(contract)
        self.assertTrue(any(phrase in error for error in errors), errors)

    def test_canonical_contract_is_semantically_valid(self) -> None:
        self.assertEqual([], self.errors())

    def test_contradictory_headline_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["identity"]["headline"] = "A different unregistered headline."
        self.assert_has_error(changed, "headline contradicts")

    def test_unknown_evidence_reference_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["claim_register"][0]["evidence_refs"].append("missing-evidence")
        self.assert_has_error(changed, "unknown evidence ref")

    def test_evidence_sensitive_claim_cannot_be_promoted_before_c02(self) -> None:
        changed = copy.deepcopy(self.contract)
        claim = next(item for item in changed["claim_register"] if item["kind"] == "evidence_sensitive")
        claim["status"] = "verified"
        self.assert_has_error(changed, "not provisional_c02")

    def test_audience_confusion_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        partner = next(item for item in changed["audiences"] if item["id"] == "product_operating_partner")
        partner["public_door"] = True
        self.assert_has_error(changed, "partnership must be non-public")

    def test_offer_overlap_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        scenario = next(item for item in changed["qualification"]["scenarios"] if item["id"] == "stalled_agent_pilot")
        scenario["facts"].update({
            "implementation_needed": True,
            "accepted_evidence_baseline": True,
            "bounded_change_scope": True,
        })
        install_rule = next(item for item in changed["qualification"]["rules"] if item["route"] == "install")
        install_rule["none"] = []
        self.assert_has_error(changed, "overlaps commercial offers")

    def test_unbounded_audit_authority_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        audit = next(item for item in changed["offer_ladder"]["items"] if item["id"] == "audit")
        audit["authority"]["mode"] = "unbounded_write"
        self.assert_has_error(changed, "Audit authority must be read-only")

    def test_missing_symbolic_range_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["offer_ladder"]["items"][0]["economics"].pop("range_id")
        self.assert_has_error(changed, "lacks symbolic price range")

    def test_numeric_price_leak_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["offer_ladder"]["items"][0]["economics"]["capacity_rule"] = "Start at $25000."
        self.assert_has_error(changed, "numeric pricing leaked")

    def test_unsupported_public_language_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["identity"]["supporting_line"] = "The best in the world at production systems."
        self.assert_has_error(changed, "unsupported public language")

    def test_private_source_and_price_leaks_fail_closed(self) -> None:
        private_errors = MODULE.validate_artifact_text("example.md", "source: /Users/example/private")
        price_errors = MODULE.validate_artifact_text("example.md", "Fee: 25000 USD")
        self.assertTrue(any("private-source marker" in error for error in private_errors), private_errors)
        self.assertTrue(any("numeric pricing" in error for error in price_errors), price_errors)


if __name__ == "__main__":
    unittest.main()
