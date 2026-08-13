#!/usr/bin/env python3
"""Hermetic focused tests for PSP-P04 generated offer artifacts."""

from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/positioning-offer-artifacts.py"
SPEC = importlib.util.spec_from_file_location("positioning_offer_artifacts", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OfferArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_contract()

    def assert_contract_error(self, contract, phrase: str) -> None:
        errors = MODULE.validate_contract(contract)
        self.assertTrue(any(phrase in error for error in errors), errors)

    def materialize(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output_dir = Path(temporary.name) / "offers"
        MODULE.write_artifacts(self.contract, output_dir)
        return output_dir

    def test_canonical_source_and_repository_artifacts_are_valid(self) -> None:
        self.assertEqual([], MODULE.validate_contract(self.contract))
        self.assertEqual([], MODULE.validate_repository(self.contract))

    def test_render_is_deterministic_and_has_exact_manifest(self) -> None:
        first = MODULE.render_artifacts(self.contract)
        second = MODULE.render_artifacts(copy.deepcopy(self.contract))
        self.assertEqual(first, second)
        self.assertEqual(MODULE.EXPECTED_FILES, set(first))

    def test_every_offer_page_covers_every_required_canonical_value(self) -> None:
        artifacts = MODULE.render_artifacts(self.contract)
        offers = MODULE._offer_map(self.contract)
        for offer_id, filename in MODULE.OFFER_FILES.items():
            with self.subTest(offer=offer_id):
                self.assertEqual(
                    [],
                    MODULE.validate_offer_page_coverage(
                        self.contract,
                        offers[offer_id],
                        artifacts[filename],
                        filename,
                    ),
                )

    def test_missing_required_offer_field_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["offer_ladder"]["items"][0].pop("handoff")
        self.assert_contract_error(changed, "missing required field: handoff")

    def test_materialized_drift_fails_closed(self) -> None:
        output_dir = self.materialize()
        path = output_dir / MODULE.OFFER_FILES["audit"]
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "one named sponsor and decision owner",
                "an unnamed sponsor",
                1,
            ),
            encoding="utf-8",
        )
        errors = MODULE.validate_artifact_directory(self.contract, output_dir)
        self.assertTrue(any("drifted from canonical YAML" in error for error in errors), errors)
        self.assertTrue(
            any("missing canonical entry_criteria" in error for error in errors),
            errors,
        )

    def test_numeric_price_leak_fails_closed(self) -> None:
        output_dir = self.materialize()
        path = output_dir / MODULE.OFFER_FILES["install"]
        path.write_text(
            path.read_text(encoding="utf-8") + "\nFee: $25,000 USD\n",
            encoding="utf-8",
        )
        errors = MODULE.validate_artifact_directory(self.contract, output_dir)
        self.assertTrue(any("numeric price leaked" in error for error in errors), errors)

    def test_bare_numeric_economics_source_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["offer_ladder"]["items"][0]["economics"]["capacity_rule"] = "Start at 25000."
        self.assert_contract_error(changed, "numeric price leaked")

    def test_private_path_and_source_leak_fail_closed(self) -> None:
        output_dir = self.materialize()
        path = output_dir / MODULE.OFFER_FILES["retainer"]
        path.write_text(
            path.read_text(encoding="utf-8") + "\nSource: /Users/example/.limen-private/session-state/record.md\n",
            encoding="utf-8",
        )
        errors = MODULE.validate_artifact_directory(self.contract, output_dir)
        self.assertTrue(any("private path or source leaked" in error for error in errors), errors)

    def test_offer_overlap_in_routing_scenario_fails_closed(self) -> None:
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
        self.assert_contract_error(changed, "offer overlap in scenario")

    def test_public_partnership_promotion_in_source_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["offer_ladder"]["secondary"]["public_cta"] = True
        self.assert_contract_error(changed, "public partnership promotion is prohibited")

    def test_partnership_no_implied_terms_boundary_fails_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["offer_ladder"]["secondary"]["promise"] = "A decision on whether to run a partnership pilot."
        self.assert_contract_error(changed, "no-implied-terms boundary missing")

    def test_public_partnership_cta_in_artifact_fails_closed(self) -> None:
        output_dir = self.materialize()
        path = output_dir / MODULE.OFFER_FILES["partnership_review"]
        path.write_text(
            path.read_text(encoding="utf-8") + f"\n{MODULE.FRONT_DOOR_MARKER} Apply for a product partnership.\n",
            encoding="utf-8",
        )
        errors = MODULE.validate_artifact_directory(self.contract, output_dir)
        self.assertTrue(any("public partnership promotion" in error for error in errors), errors)
        self.assertTrue(
            any("must not contain a front-door CTA" in error for error in errors),
            errors,
        )

    def test_front_door_ctas_route_only_to_audit(self) -> None:
        artifacts = MODULE.render_artifacts(self.contract)
        self.assertEqual([], MODULE.validate_front_door_ctas(artifacts))
        partner = artifacts[MODULE.OFFER_FILES["partnership_review"]]
        self.assertNotIn(MODULE.FRONT_DOOR_MARKER, partner)


if __name__ == "__main__":
    unittest.main()
