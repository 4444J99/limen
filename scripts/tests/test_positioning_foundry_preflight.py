import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_runtime_assignment_requirements_are_fail_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["assignment_requirements"]["leaves"]["PSP-P13-W08"]["effort"] = "xhigh"
        self.assertIn(
            "assignment requirements drift from the canonical runtime registry",
            MODULE.validate_contract(changed),
        )

    def test_upstream_c02_and_c03_bindings_are_fail_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["live_sources"][1]["merge_commit"] = "0" * 40
        changed["dependency_boundary"]["c03_checkpoint"]["reader_gate"]["assignment_requirement"]["effort"] = "medium"
        errors = MODULE.validate_contract(changed)
        self.assertIn(
            "c02_estate_census must remain bound to its accepted merged commit",
            errors,
        )
        self.assertIn("C03 accepted checkpoint or reader gate drift", errors)

    def test_prepared_chunk_heads_are_exact_and_not_closure(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["dependency_boundary"]["prepared_chunks"]["PSP-C10"]["closed"] = True
        changed["dependency_boundary"]["formal_predecessor"]["source_head"] = "f" * 40
        errors = MODULE.validate_contract(changed)
        self.assertIn("C04-C10 prepared checkpoint heads drift", errors)
        self.assertIn("C10 predecessor checkpoint head drift", errors)

    def test_c10_readiness_source_lock_is_exact_and_non_closing(self) -> None:
        predecessor = self.contract["dependency_boundary"]["formal_predecessor"]
        self.assertEqual(MODULE.EXPECTED_C10_INTEGRATION["source_head"], predecessor["source_head"])
        self.assertEqual(
            MODULE.EXPECTED_C10_INTEGRATION["integrated_main_head"],
            predecessor["integrated_main_head"],
        )
        self.assertEqual(
            MODULE.EXPECTED_C10_INTEGRATION["receipt_sha256"],
            predecessor["receipt_sha256"],
        )
        self.assertTrue(all(row["counts_as_closure"] is False for row in predecessor["source_bindings"]))
        changed = copy.deepcopy(self.contract)
        changed["dependency_boundary"]["formal_predecessor"]["source_bindings"][0]["counts_as_closure"] = True
        self.assertIn(
            "C10 integrated readiness source-lock drift",
            MODULE.validate_contract(changed),
        )

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
        self.assertEqual(
            MODULE.EXPECTED_C10_INTEGRATION["source_head"],
            receipt["source_lock"]["source_head"],
        )
        self.assertEqual(
            MODULE.EXPECTED_C10_INTEGRATION["integrated_main_head"],
            receipt["source_lock"]["integrated_main_head"],
        )
        self.assertFalse(receipt["source_lock"]["counts_as_closure"])

    def test_contract_root_schema_and_duplicate_members_fail_closed(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["unexpected"] = "credential-like-surplus"
        self.assertIn(
            "contract must use the exact public-safe root schema",
            MODULE.validate_contract(changed),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"status":"safe","status":"shadowed"}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.PreflightError, "duplicate JSON member: status"):
                MODULE.load_json(path)

    def test_private_snapshot_rows_are_opaque(self) -> None:
        private_rows = [row for row in self.snapshot["candidates"] if row["visibility"] == "private"]
        self.assertEqual(8, len(private_rows))
        self.assertTrue(all(row["repository"] is None for row in private_rows))
        self.assertTrue(all(row["candidate_id"].startswith("private-candidate-") for row in private_rows))
        self.assertTrue(all(set(row) == MODULE.PRIVATE_CANDIDATE_KEYS for row in private_rows))
        self.assertTrue(all(row["demand"] == MODULE.PRIVATE_DEMAND for row in private_rows))
        self.assertTrue(all(row["readiness"] == MODULE.PRIVATE_READINESS for row in private_rows))
        self.assertTrue(all(row["economics"] == MODULE.PRIVATE_ECONOMICS for row in private_rows))
        self.assertTrue(all("current_state" not in row and "fork" not in row for row in private_rows))

    def test_private_snapshot_detail_and_summary_tampering_fail_closed(self) -> None:
        changed = copy.deepcopy(self.snapshot)
        private = next(row for row in changed["candidates"] if row["visibility"] == "private")
        private["current_state"] = "archived"
        changed["candidate_denominator"]["visibility"]["private"] -= 1
        changed["score_distribution"]["demand_tiers"]["E0"] -= 1
        errors = MODULE.validate_snapshot(changed, self.contract)
        self.assertTrue(any("private row shape" in error for error in errors))
        self.assertIn("snapshot candidate visibility summary drift", errors)
        self.assertIn("snapshot score distribution drift", errors)

    def test_public_snapshot_rows_bind_fork_fact(self) -> None:
        public_rows = [row for row in self.snapshot["candidates"] if row["visibility"] == "public"]
        self.assertTrue(all(set(row) == MODULE.PUBLIC_CANDIDATE_KEYS for row in public_rows))
        self.assertTrue(all(isinstance(row["fork"], bool) for row in public_rows))

    def test_snapshot_sources_are_inventory_only(self) -> None:
        source_rows = {row["id"]: row for row in self.contract["live_sources"]}
        source_ids = self.contract["candidate_inventory"]["source_ids"]
        self.assertEqual(
            [source_rows[source_id]["url"] for source_id in source_ids],
            self.snapshot["sources"],
        )
        self.assertNotIn(source_rows["p02_closure"]["url"], self.snapshot["sources"])

    def test_live_compare_binds_repository_digest_and_score_distribution(self) -> None:
        live = copy.deepcopy(self.snapshot)
        live["census"]["repository_identity_sha256"] = "0" * 64
        live["score_distribution"]["demand_tiers"]["E0"] -= 1
        errors = MODULE.compare_live_snapshot(self.snapshot, live)
        self.assertIn("live snapshot drift at census.repository_identity_sha256", errors)
        self.assertIn("live snapshot drift at score_distribution", errors)

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

    def test_external_contract_and_snapshot_overrides_are_reported_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract_path = root / "contract.json"
            snapshot_path = root / "snapshot.json"
            contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
            snapshot_path.write_text(json.dumps(self.snapshot), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--contract",
                    str(contract_path),
                    "--snapshot",
                    str(snapshot_path),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(str(contract_path), payload["contract"])
        self.assertEqual(str(snapshot_path), payload["snapshot"])

    def test_live_snapshot_write_refuses_invalid_generated_output(self) -> None:
        invalid = copy.deepcopy(self.snapshot)
        invalid["candidates"][0]["unexpected"] = "shape drift"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist.json"
            argv = [str(SCRIPT), "--live", "--write-snapshot", str(output), "--json"]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(MODULE, "collect_live_repositories", return_value=([], [])),
                mock.patch.object(MODULE, "build_snapshot", return_value=invalid),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = MODULE.main()
            self.assertEqual(1, result)
            self.assertFalse(output.exists())

    def test_live_snapshot_write_rejects_drill_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist.json"
            argv = [str(SCRIPT), "--live", "--drills", "--write-snapshot", str(output), "--json"]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                result = MODULE.main()
            self.assertEqual(1, result)
            self.assertFalse(output.exists())

    def test_live_snapshot_write_still_validates_the_tracked_verification_input(self) -> None:
        invalid_tracked = copy.deepcopy(self.snapshot)
        invalid_tracked["status"] = "invalid"
        generated = copy.deepcopy(self.snapshot)
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "invalid-tracked.json"
            output = Path(directory) / "must-not-exist.json"
            snapshot_path.write_text(json.dumps(invalid_tracked), encoding="utf-8")
            argv = [
                str(SCRIPT),
                "--live",
                "--verify-live-snapshot",
                "--snapshot",
                str(snapshot_path),
                "--write-snapshot",
                str(output),
                "--json",
            ]
            stdout = io.StringIO()
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(MODULE, "collect_live_repositories", return_value=([], [])),
                mock.patch.object(MODULE, "build_snapshot", return_value=generated),
                contextlib.redirect_stdout(stdout),
            ):
                result = MODULE.main()
            self.assertEqual(1, result)
            self.assertFalse(output.exists())
            self.assertIn("snapshot status must remain PREPARED/PREFLIGHT", json.loads(stdout.getvalue())["errors"])


if __name__ == "__main__":
    unittest.main()
