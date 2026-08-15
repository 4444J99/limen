import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/positioning-foundry-handoff.py"
VERIFY_SCRIPT = ROOT / "docs/positioning/foundry/psp-c11/verify_technical_readiness.py"
SPEC = importlib.util.spec_from_file_location("psp_c11_handoff", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
VERIFY_SPEC = importlib.util.spec_from_file_location("psp_c11_verify", VERIFY_SCRIPT)
assert VERIFY_SPEC and VERIFY_SPEC.loader
VERIFY = importlib.util.module_from_spec(VERIFY_SPEC)
sys.modules[VERIFY_SPEC.name] = VERIFY
VERIFY_SPEC.loader.exec_module(VERIFY)


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.contract = MODULE.load_json(MODULE.CONTRACT)
        self.base = MODULE.BASE.load_json(MODULE.BASE.CONTRACT)
        self.snapshot = MODULE.BASE.load_json(MODULE.BASE.SNAPSHOT)
        self.package = MODULE.build_package(self.contract, self.snapshot)

    def test_contract_and_package(self):
        self.assertEqual([], MODULE.validate_contract(self.contract))
        self.assertEqual([], MODULE.validate_package(self.package, self.contract, self.snapshot))

    def test_c02_binding_tamper(self):
        value = copy.deepcopy(self.contract)
        value["source"]["c02"]["merge_commit"] = "0" * 40
        self.assertIn("C02 classification binding drift", MODULE.validate_contract(value))
        value = copy.deepcopy(self.contract)
        value["source"]["c02"]["order"].reverse()
        self.assertIn("C02 taxonomy drift", MODULE.validate_contract(value))

    def test_c10_source_lock_tamper(self):
        self.assertEqual(MODULE.BASE.EXPECTED_C10_INTEGRATION, self.contract["source"]["c10"])
        self.assertTrue(
            all(row["counts_as_closure"] is False for row in self.contract["source"]["c10"]["source_bindings"])
        )
        value = copy.deepcopy(self.contract)
        value["source"]["c10"]["receipt_sha256"] = "0" * 64
        self.assertIn(
            "C10 integrated readiness source-lock drift",
            MODULE.validate_contract(value),
        )

    def test_contract_root_schema_and_duplicate_members_fail_closed(self):
        value = copy.deepcopy(self.contract)
        value["unexpected"] = "surplus"
        self.assertIn(
            "handoff contract must use the exact public-safe root schema",
            MODULE.validate_contract(value),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"status":"safe","status":"shadowed"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON member: status"):
                MODULE.load_json(path)

    def test_62_deterministic_non_binding_records(self):
        self.assertEqual(62, self.package["classification"]["count"])
        self.assertEqual(62, self.package["decision_summary"]["count"])
        self.assertEqual(self.package, MODULE.build_package(self.contract, self.snapshot))
        for row in self.package["decisions"]:
            self.assertFalse(row["binding"])
            self.assertFalse(row["transfer_eligible"])
            self.assertEqual([], row["external_effects"])
            self.assertEqual("owner_custody_unchanged", row["authority_state"])

    def test_public_lifecycle_fields_are_source_locked(self):
        changed = copy.deepcopy(self.snapshot)
        row = next(candidate for candidate in changed["candidates"] if candidate["visibility"] == "public")
        row["current_state"] = "archived" if row["current_state"] != "archived" else "active_repository"
        row["preflight_disposition"] = "park" if row["preflight_disposition"] != "park" else "experiment"
        with self.assertRaisesRegex(VERIFY.AuditError, "accepted public candidate lifecycle binding is invalid"):
            VERIFY.candidate_projection_digest(changed)

    def test_c02_comparison_and_private_withholding(self):
        rows = self.package["classification"]["records"]
        public = [item for item in rows if item["visibility"] == "public"]
        private = [item for item in rows if item["visibility"] == "private"]
        self.assertEqual(54, len(public))
        self.assertEqual(8, len(private))
        self.assertTrue(all(item["classification"]["primary"] in MODULE.TAX for item in public))
        for row in private:
            self.assertIsNone(row["repository"])
            self.assertIsNone(row["classification"]["primary"])
            self.assertIsNone(row["classification"]["governance"])
            self.assertEqual("private_classification_withheld", row["classification"]["comparison"])

    def test_authority_and_privacy_fail_closed(self):
        self.assertEqual(MODULE.ACTIONS, self.contract["authority"]["actions"])
        self.assertEqual("allow", MODULE.ACTIONS["analysis"])
        self.assertTrue(all(value == "deny" for key, value in MODULE.ACTIONS.items() if key != "analysis"))
        self.assertEqual(MODULE.FORBIDDEN, set(self.contract["privacy"]["public_forbidden"]))
        self.assertEqual(
            "no_operator_appointed_owner_custody_unchanged",
            self.contract["authority"]["state"],
        )

    def test_five_rollback_drills_have_no_effect(self):
        receipt = MODULE.rollback_drills(self.contract)
        self.assertEqual("pass", receipt["status"])
        self.assertEqual(5, len(receipt["drills"]))
        self.assertFalse(receipt["human_acceptance_simulated"])
        self.assertFalse(receipt["observed_pilot"])
        self.assertEqual([], receipt["external_effects"])
        self.assertEqual("owner_unchanged", receipt["final_custody"])
        self.assertEqual(MODULE.TRIGGERS, {item["id"] for item in receipt["drills"]})
        self.assertTrue(all(item["external_effects"] == [] for item in receipt["drills"]))

    def test_rollback_decision_mapping_is_exact(self):
        changed = copy.deepcopy(self.contract)
        changed["rollback"]["triggers"][1]["decision"] = "proceed"
        self.assertIn("rollback contract drift", MODULE.validate_contract(changed))
        self.assertEqual("fail", MODULE.rollback_drills(changed)["status"])

    def test_public_fork_fact_reaches_governance_classifier(self):
        row = {
            "visibility": "public",
            "repository": "owner/example",
            "current_state": "active_repository",
            "fork": True,
            "readiness": {"evidence": []},
        }
        with mock.patch.object(MODULE.GITVS, "classify_repo", return_value="portal_public") as classify_repo:
            MODULE.classify(row, self.contract, {}, {"grants": {}})
        self.assertIs(classify_repo.call_args.args[2]["fork"], True)

    def test_public_candidate_current_state_and_preflight_disposition_affect_decision_basis(self):
        row = {
            "candidate_id": "candidate-x",
            "visibility": "public",
            "repository": "owner/example",
            "current_state": "archived",
            "preflight_disposition": "park",
            "fork": False,
            "demand": {"tier": "E3", "score": 60, "evidence": ["x"], "next_experiment": "n", "stop_condition": "s"},
            "readiness": {"band": "diligence_required", "metadata_screen_score": 40, "custody_risk": "r"},
            "economics": {"status": "ok"},
        }
        classification = {"comparison": "aligned_product"}
        decision = MODULE.decision(row, classification, self.contract)
        self.assertEqual("park", decision["decision"])

    def test_decision_tamper(self):
        value = copy.deepcopy(self.package)
        value["decisions"][0]["binding"] = True
        errors = MODULE.validate_package(value, self.contract, self.snapshot)
        self.assertTrue(any("binding or transfer overclaim" in item for item in errors))
        self.assertIn("decision digest drift", errors)

    def test_private_projection_tamper(self):
        value = copy.deepcopy(self.package)
        row = next(item for item in value["classification"]["records"] if item["visibility"] == "private")
        row["repository"] = "private/name"
        row["classification"]["primary"] = "products"
        errors = MODULE.validate_package(value, self.contract, self.snapshot)
        self.assertTrue(any("private detail exposed" in item for item in errors))
        self.assertIn("classification digest drift", errors)

    def test_external_effect_tamper(self):
        value = copy.deepcopy(self.package)
        value["external_effects"] = ["send"]
        self.assertIn(
            "package recorded external effects",
            MODULE.validate_package(value, self.contract, self.snapshot),
        )

    def test_package_source_lock_tamper(self):
        value = copy.deepcopy(self.package)
        value["source_lock"]["c10"]["source_bindings"][0]["counts_as_closure"] = True
        self.assertIn(
            "package source-lock drift",
            MODULE.validate_package(value, self.contract, self.snapshot),
        )


if __name__ == "__main__":
    unittest.main()
