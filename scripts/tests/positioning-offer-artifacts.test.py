#!/usr/bin/env python3
"""Hermetic focused tests for PSP-P04 generated offer artifacts."""

from __future__ import annotations

import copy
import importlib.util
import json
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

    @staticmethod
    def retainer(contract):
        return next(item for item in contract["offer_ladder"]["items"] if item["id"] == "retainer")

    def test_canonical_source_and_repository_artifacts_are_valid(self) -> None:
        self.assertEqual([], MODULE.validate_contract(self.contract))
        self.assertEqual([], MODULE.validate_repository(self.contract))

    def test_render_is_deterministic_and_has_exact_manifest(self) -> None:
        first = MODULE.render_artifacts(self.contract)
        second = MODULE.render_artifacts(copy.deepcopy(self.contract))
        self.assertEqual(first, second)
        self.assertEqual(MODULE.EXPECTED_FILES, set(first))

    def test_retainer_capacity_artifact_exactly_binds_the_canonical_model(self) -> None:
        artifacts = MODULE.render_artifacts(self.contract)
        payload = json.loads(artifacts[MODULE.CAPACITY_FILE])
        retainer = self.retainer(self.contract)
        self.assertEqual("PSP-P04-W03", payload["work_item"])
        self.assertEqual(retainer["capacity_model"], payload["capacity_model"])
        self.assertEqual(retainer["authority"], payload["offer"]["authority"])
        self.assertEqual(retainer["timeline"], payload["offer"]["timeline"])
        rendered = artifacts[MODULE.OFFER_FILES["retainer"]]
        self.assertIn("## Capacity model", rendered)
        self.assertIn("**Included delivery days:** `6`", rendered)
        self.assertIn("**On-call:** `false`", rendered)
        self.assertIn("**Emergency response:** `false`", rendered)

    def test_retainer_capacity_model_requires_an_exact_mapping(self) -> None:
        malformed = copy.deepcopy(self.contract)
        self.retainer(malformed)["capacity_model"] = "unbounded"
        self.assert_contract_error(malformed, "capacity_model must be a non-empty mapping")

        extra = copy.deepcopy(self.contract)
        self.retainer(extra)["capacity_model"]["hidden_capacity"] = True
        self.assert_contract_error(extra, "capacity_model fields must be exactly")

    def test_retainer_capacity_model_rejects_non_string_keys_without_crashing(self) -> None:
        malformed = copy.deepcopy(self.contract)
        self.retainer(malformed)["capacity_model"][1] = "hidden capacity"
        errors = MODULE.validate_contract(malformed)
        self.assertTrue(any("capacity_model keys must be strings" in error for error in errors), errors)

    def test_duplicate_yaml_members_fail_before_semantic_validation(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "contract.yaml"
        source = MODULE.CONTRACT_PATH.read_text(encoding="utf-8")
        source = source.replace(
            "        included_delivery_days: 6\n",
            "        included_delivery_days: 30\n        included_delivery_days: 6\n",
            1,
        )
        path.write_text(source, encoding="utf-8")
        with self.assertRaisesRegex(MODULE.OfferArtifactValidationError, "duplicate YAML mapping key"):
            MODULE.load_contract(path)

    def test_retainer_capacity_allocation_is_finite_and_exact(self) -> None:
        changed = copy.deepcopy(self.contract)
        capacity = self.retainer(changed)["capacity_model"]
        capacity["allocation"]["uncommitted_days"] = 2
        self.assert_contract_error(changed, "allocation must equal included_delivery_days exactly")

        boolean = copy.deepcopy(self.contract)
        self.retainer(boolean)["capacity_model"]["allocation"]["approved_change_days"] = True
        self.assert_contract_error(boolean, "allocation values must be non-boolean integers")

    def test_retainer_capacity_hours_are_derived_exactly(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["included_hours"] = 35
        self.assert_contract_error(changed, "included_hours must exactly equal")

    def test_retainer_numeric_scalars_are_allowlisted_by_exact_path(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["exhaustion_route"] = 25000
        self.assert_contract_error(changed, "numeric fields must match the explicit non-monetary path allowlist")

    def test_retainer_all_service_activity_consumes_one_ledger(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["consumption_rule"] = "Only approved changes consume capacity."
        self.assert_contract_error(changed, "every service activity from one finite capacity ledger")

    def test_retainer_quantity_limits_are_finite(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["quantity_limits"]["teams"] = 2
        self.assert_contract_error(changed, "one team and one active change")

        boolean = copy.deepcopy(self.contract)
        self.retainer(boolean)["capacity_model"]["quantity_limits"]["repositories"] = True
        self.assert_contract_error(boolean, "quantity limits must be finite positive integers")

    def test_retainer_capacity_does_not_roll_over_or_imply_standby(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["rollover"] = True
        self.assert_contract_error(changed, "must not roll over or imply standby")

    def test_retainer_response_envelope_has_no_hidden_on_call(self) -> None:
        changed = copy.deepcopy(self.contract)
        response = self.retainer(changed)["capacity_model"]["response_envelope"]
        response["on_call"] = True
        response["emergency_response"] = True
        self.assert_contract_error(changed, "no on-call or emergency SLA")

    def test_retainer_response_envelope_names_operating_clock_and_pause_conditions(self) -> None:
        changed = copy.deepcopy(self.contract)
        response = self.retainer(changed)["capacity_model"]["response_envelope"]
        response["timezone"] = "wherever the provider happens to be"
        response["clock_pause_conditions"] = ["any delay"]
        self.assert_contract_error(changed, "must name channel, timezone, hours, pause conditions")

        resolution = copy.deepcopy(self.contract)
        self.retainer(resolution)["capacity_model"]["response_envelope"]["resolution_sla"] = True
        self.assert_contract_error(resolution, "must not promise a resolution SLA")

    def test_retainer_response_targets_are_bounded_and_ordered(self) -> None:
        changed = copy.deepcopy(self.contract)
        response = self.retainer(changed)["capacity_model"]["response_envelope"]
        response["acknowledgement_target_business_days"] = 6
        response["decision_target_business_days"] = 5
        self.assert_contract_error(changed, "response targets must be ordered")

    def test_retainer_decision_rights_forbid_executive_substitution(self) -> None:
        changed = copy.deepcopy(self.contract)
        rights = self.retainer(changed)["capacity_model"]["decision_rights"]
        rights["internal_owner"] = "The provider owns daily decisions."
        rights["provider"] = "Acts as the executive operator."
        self.assert_contract_error(changed, "preserve internal ownership and bounded provider authority")

        prohibited = copy.deepcopy(self.contract)
        self.retainer(prohibited)["capacity_model"]["decision_rights"]["provider_prohibited_actions"].remove(
            "approve production effects"
        )
        self.assert_contract_error(prohibited, "preserve internal ownership and bounded provider authority")

    def test_retainer_capacity_lists_exactly_bind_the_offer(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["included_artifacts"].append("informal status call")
        self.assert_contract_error(changed, "included_artifacts must exactly match the canonical offer")

        duplicated = copy.deepcopy(self.contract)
        capacity = self.retainer(duplicated)["capacity_model"]
        capacity["exclusions"].append(capacity["exclusions"][0])
        self.assert_contract_error(duplicated, "exclusions must exactly match the canonical offer")

    def test_retainer_renewal_and_exit_are_explicit(self) -> None:
        changed = copy.deepcopy(self.contract)
        self.retainer(changed)["capacity_model"]["renewal_exit"]["exit_steps"] = ["send a summary"]
        self.assert_contract_error(changed, "renewal and exit must be explicit")

    def test_retainer_escalation_routes_are_deterministic(self) -> None:
        changed = copy.deepcopy(self.contract)
        routes = self.retainer(changed)["capacity_model"]["escalation_routes"]
        routes["missing_owner"] = "Continue while searching for an owner."
        self.assert_contract_error(changed, "deterministically cover capacity, owner, authority")

    def test_retainer_acceptance_requires_capacity_ledger_and_dated_verdict(self) -> None:
        changed = copy.deepcopy(self.contract)
        retainer = self.retainer(changed)
        retainer["evidence"]["acceptance"] = "The sponsor says the period is complete."
        retainer["evidence"]["artifacts"].remove("capacity ledger")
        retainer["capacity_model"]["included_artifacts"].remove("capacity ledger")
        self.assert_contract_error(changed, "acceptance must prove capacity consumption")

    def test_materialized_capacity_model_drift_fails_closed(self) -> None:
        output_dir = self.materialize()
        path = output_dir / MODULE.CAPACITY_FILE
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["capacity_model"]["included_delivery_days"] = 30
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        errors = MODULE.validate_artifact_directory(self.contract, output_dir)
        self.assertTrue(any("drifted from canonical YAML" in error for error in errors), errors)

    def test_every_materialized_json_file_is_manifested_and_safety_scanned(self) -> None:
        output_dir = self.materialize()
        extra = output_dir / "obsolete.json"
        extra.write_text('{"source": "/Users/example/private", "fee": "25000 USD"}\n', encoding="utf-8")
        errors = MODULE.validate_artifact_directory(self.contract, output_dir)
        self.assertTrue(any("unexpected unmanaged offer artifact: obsolete.json" in error for error in errors), errors)
        self.assertTrue(any("private path or source leaked" in error for error in errors), errors)
        self.assertTrue(any("numeric price leaked" in error for error in errors), errors)

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

    def test_install_requires_named_sponsor_owner_team_and_pipeline(self) -> None:
        changed = copy.deepcopy(self.contract)
        install = next(item for item in changed["offer_ladder"]["items"] if item["id"] == "install")
        install["entry_criteria"].remove("one named sponsor, internal owner, team, and pipeline")
        self.assert_contract_error(changed, "requires one named sponsor, internal owner, team, and pipeline")

    def test_install_requires_acceptance_tests_and_handoff_owner_before_start(self) -> None:
        changed = copy.deepcopy(self.contract)
        install = next(item for item in changed["offer_ladder"]["items"] if item["id"] == "install")
        install["entry_criteria"].remove("acceptance tests and a handoff owner agreed before work starts")
        self.assert_contract_error(changed, "requires acceptance tests and a handoff owner before work starts")

    def test_install_requires_finite_acceptance_and_internal_owner_handoff(self) -> None:
        changed = copy.deepcopy(self.contract)
        install = next(item for item in changed["offer_ladder"]["items"] if item["id"] == "install")
        install["timeline"] = "Continue until the platform is complete."
        install["evidence"]["acceptance"] = "The provider declares the implementation complete."
        install["handoff"] = "Provide a summary when convenient."
        self.assert_contract_error(changed, "requires finite acceptance evidence and a named internal-owner handoff")

    def test_install_explicitly_excludes_enterprise_platform_rewrite(self) -> None:
        changed = copy.deepcopy(self.contract)
        install = next(item for item in changed["offer_ladder"]["items"] if item["id"] == "install")
        install["exclusions"].remove("enterprise-wide platform rewrite")
        self.assert_contract_error(changed, "explicitly exclude an enterprise-wide platform rewrite")

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
