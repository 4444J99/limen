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

    @staticmethod
    def retainer(contract):
        return next(item for item in contract["offer_ladder"]["items"] if item["id"] == "retainer")

    def test_canonical_contract_is_semantically_valid(self) -> None:
        self.assertEqual([], self.errors())

    def test_repository_artifacts_match_live_registry_contract(self) -> None:
        self.assertEqual([], MODULE.validate_repository(self.contract))

    def test_contradictory_headline_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["identity"]["headline"] = "A different unregistered headline."
        self.assert_has_error(changed, "headline contradicts")

    def test_unknown_evidence_reference_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["claim_register"][0]["evidence_refs"].append("missing-evidence")
        self.assert_has_error(changed, "unknown evidence ref")

    def test_accepted_evidence_sensitive_claim_cannot_drift(self) -> None:
        changed = copy.deepcopy(self.contract)
        claim = next(item for item in changed["claim_register"] if item["kind"] == "evidence_sensitive")
        claim["status"] = "provisional_c02"
        self.assert_has_error(changed, "status drifted")

    def test_accepted_p02_binding_cannot_drift(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["contract"]["accepted_state"]["p02"]["accepted_head"] = "0" * 40
        self.assert_has_error(changed, "accepted P02 binding drifted")

    def test_accepted_p03_receipt_binding_cannot_drift(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["contract"]["accepted_state"]["p03_accepted_work"][5]["receipt"] = "https://example.invalid"
        self.assert_has_error(changed, "accepted P03 W01-W06 bindings drifted")

    def test_reader_gate_cannot_count_synthetic_or_model_responses(self) -> None:
        changed = copy.deepcopy(self.contract)
        gate = changed["contract"]["accepted_state"]["active_reader_gate"]
        gate["synthetic_or_model_readers_allowed"] = True
        self.assert_has_error(changed, "reject synthetic and model readers")

    def test_reader_gate_count_cannot_advance_without_durable_evidence(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["contract"]["accepted_state"]["active_reader_gate"]["current_valid_readers"] = 1
        self.assert_has_error(changed, "must reflect durable collected evidence")

    def test_reader_gate_blocks_phase_close_but_not_eligible_leaf_execution(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["contract"]["accepted_state"]["p04"]["state"] = "staged_dependency_blocked"
        self.assert_has_error(changed, "leaf-execution and phase-close dependency binding drifted")

    def test_shared_retainer_capacity_semantics_cannot_false_green(self) -> None:
        changed = copy.deepcopy(self.contract)
        capacity = self.retainer(changed)["capacity_model"]
        capacity["included_hours"] = capacity["included_hours"] + 1
        self.assert_has_error(changed, "included_hours must exactly equal")

        unbounded = copy.deepcopy(self.contract)
        self.retainer(unbounded)["capacity_model"]["rollover"] = True
        self.assert_has_error(unbounded, "must not roll over or imply standby")

    def test_audience_confusion_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        partner = next(item for item in changed["audiences"] if item["id"] == "product_operating_partner")
        partner["public_door"] = True
        self.assert_has_error(changed, "partnership must be non-public")

    def test_offer_overlap_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        scenario = next(item for item in changed["qualification"]["scenarios"] if item["id"] == "stalled_agent_pilot")
        scenario["facts"].update(
            {
                "implementation_needed": True,
                "accepted_evidence_baseline": True,
                "bounded_change_scope": True,
            }
        )
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

    def test_threat_language_leaf_cannot_regress_to_problem_map(self) -> None:
        matrix = MODULE.P03_MATRIX_PATH.read_text()
        changed = "\n".join(
            line.replace("`interview_threat_contract`", "`expensive_problem_map`")
            if "| PSP-P03-W06 |" in line
            else line
            for line in matrix.splitlines()
        )
        errors = MODULE.validate_p03_matrix(changed)
        self.assertTrue(any("must map to interview_threat_contract" in error for error in errors), errors)

    def test_p04_matrix_cannot_reintroduce_a_phase_wide_leaf_block(self) -> None:
        matrix = MODULE.P04_MATRIX_PATH.read_text()
        self.assertEqual([], MODULE.validate_p04_matrix(matrix, self.contract))
        changed = matrix.replace(
            "Independently eligible P04 leaves may merge and receipt-close after their own predicates pass",
            "all P04 leaves remain open until PSP-P03 closes",
            1,
        )
        errors = MODULE.validate_p04_matrix(changed, self.contract)
        self.assertTrue(any("stale phase-wide leaf block" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
