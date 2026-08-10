import copy
import datetime as dt
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/positioning-foundry-preflight.py"
SPEC = importlib.util.spec_from_file_location("positioning_foundry_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PositioningFoundryPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_json(MODULE.CONTRACT)
        self.snapshot = MODULE.load_json(MODULE.SNAPSHOT)

    def test_tracked_contract_and_snapshot_are_valid(self) -> None:
        self.assertEqual([], MODULE.validate_contract(self.contract))
        self.assertEqual([], MODULE.validate_snapshot(self.snapshot, self.contract))

    def test_exact_leaf_assignments_are_fail_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["leaf_assignments"]["PSP-P13-W08"]["effort"] = "xhigh"
        self.assertIn("leaf model, effort, or effect assignment drift", MODULE.validate_contract(changed))

    def test_observed_pilot_or_transfer_claim_is_rejected(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["bounded_pilot"]["observed_pilot"] = True
        changed["bounded_pilot"]["rights_transferred"] = True
        errors = MODULE.validate_contract(changed)
        self.assertIn("bounded_pilot.observed_pilot must remain false", errors)
        self.assertIn("bounded_pilot.rights_transferred must remain false", errors)

    def test_all_human_gates_are_unique_and_unpulled(self) -> None:
        gates = self.contract["human_gates"]
        self.assertEqual(MODULE.REQUIRED_GATES, {row["id"] for row in gates})
        self.assertTrue(all(row["state"] == "unpulled" for row in gates))

    def test_synthetic_operator_routes_cover_all_decisions(self) -> None:
        receipt = MODULE.run_synthetic_drills(self.contract)
        routes = {row["route"] for row in receipt["operator_cases"]}
        self.assertEqual({"proceed", "diligence", "trial", "decline", "human_review"}, routes)
        self.assertTrue(all(row["pass"] for row in receipt["operator_cases"]))

    def test_pre_terms_access_is_denied(self) -> None:
        receipt = MODULE.run_synthetic_drills(self.contract)
        decisions = {row["drill_id"]: row["decision"] for row in receipt["access_drills"]}
        self.assertEqual("deny", decisions["early-credential"])
        self.assertEqual("deny", decisions["early-private-source"])
        self.assertEqual("deny", decisions["early-license"])

    def test_synthetic_replay_never_simulates_acceptance_or_external_effects(self) -> None:
        receipt = MODULE.run_synthetic_drills(self.contract)
        self.assertTrue(receipt["synthetic_only"])
        self.assertFalse(receipt["human_acceptance_simulated"])
        self.assertFalse(receipt["observed_pilot"])
        self.assertEqual([], receipt["external_effects"])
        self.assertTrue(all(not row["external_effect"] for row in receipt["lifecycle_replay"]))
        self.assertEqual("owner_unchanged", receipt["final_custody"])

    def test_private_snapshot_rows_are_opaque(self) -> None:
        private_rows = [row for row in self.snapshot["candidates"] if row["visibility"] == "private"]
        self.assertEqual(8, len(private_rows))
        self.assertTrue(all(row["repository"] is None for row in private_rows))
        self.assertTrue(all(row["candidate_id"].startswith("private-candidate-") for row in private_rows))
        self.assertTrue(all(row["demand"]["tier"] == "E0" for row in private_rows))

    def test_every_candidate_has_demand_readiness_economics_and_stop_rules(self) -> None:
        self.assertEqual(62, len(self.snapshot["candidates"]))
        for row in self.snapshot["candidates"]:
            self.assertTrue(row["demand"]["evidence"])
            self.assertTrue(row["demand"]["next_experiment"])
            self.assertTrue(row["demand"]["stop_condition"])
            self.assertTrue(row["readiness"]["unverified_dimensions"])
            self.assertTrue(row["readiness"]["custody_risk"])
            self.assertTrue(row["economics"]["hypothesis"])
            self.assertTrue(row["economics"]["transfer_trigger"])
            self.assertFalse(row["transfer_eligible"])

    def test_metadata_demand_never_crosses_the_contract_cap(self) -> None:
        row = {
            "private": False,
            "stargazers_count": 1000,
            "forks_count": 1000,
            "subscribers_count": 1000,
        }
        score = MODULE.score_demand(row, self.contract["demand_model"])
        self.assertEqual(self.contract["demand_model"]["metadata_cap"], score["score"])
        self.assertEqual("E2", score["tier"])

    def test_readiness_screen_never_claims_full_diligence(self) -> None:
        row = {
            "private": False,
            "archived": False,
            "default_branch": "main",
            "pushed_at": "2026-08-10T00:00:00Z",
            "license": {"spdx_id": "MIT"},
            "homepage": "https://example.invalid",
        }
        score = MODULE.score_readiness(
            row,
            self.contract["readiness_model"],
            dt.datetime(2026, 8, 10, 12, tzinfo=dt.UTC),
        )
        self.assertEqual(self.contract["readiness_model"]["metadata_screen_cap"], score["metadata_screen_score"])
        self.assertIn("exact_head_build_test", score["unverified_dimensions"])
        self.assertIn("runtime_liveness", score["unverified_dimensions"])

    def test_tracked_synthetic_receipt_matches_current_drill(self) -> None:
        tracked = json.loads(
            (ROOT / "docs/positioning/foundry/psp-c11/synthetic-drill-receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(tracked, MODULE.run_synthetic_drills(self.contract))


if __name__ == "__main__":
    unittest.main()
