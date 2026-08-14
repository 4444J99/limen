import copy
import importlib.util
import hashlib
import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/positioning-proof-preflight.py"
SPEC = importlib.util.spec_from_file_location("positioning_proof_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PositioningProofPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_contract(MODULE.DEFAULT_CONTRACT)

    def _valid_w07_binding(self) -> tuple[dict[str, object], dict[str, object]]:
        head = "a" * 40
        response_path = "docs/positioning/program/w07_blinded_reader_responses.json"
        receipt = {
            "work_id": "PSP-P03-W07",
            "outcome": "succeeded",
            "observed_heads": {"organvm/limen": head},
            "changed_paths": [response_path],
            "evidence_urls": [f"https://github.com/organvm/limen/blob/{head}/{response_path}"],
            "predicate": {
                "command": f"python3 {MODULE.W07_VALIDATOR_PATH} {response_path}",
                "exit_code": 0,
            },
            "reader_evidence": {
                "reader_count": 5,
                "independent_reader_count": 5,
                "synthetic_or_model_reader_count": 0,
                "unresolved_authority_objections": 0,
                "total_score": 20,
                "role_matches": 4,
                "buyer_matches": 4,
                "cta_matches": 4,
                "response_set_path": response_path,
                "response_set_sha256": "b" * 64,
                "decision_memo_sha256": "c" * 64,
            },
        }
        digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        binding = {
            "work_id": "PSP-P03-W07",
            "issue_url": "https://github.com/organvm/limen/issues/2188",
            "url": "https://github.com/organvm/limen/issues/2188#issuecomment-1",
            "sha256": digest,
            "receipt": receipt,
        }
        live = {
            "status": "pass",
            "work_id": "PSP-P03-W07",
            "receipt_url": binding["url"],
            "receipt_sha256": digest,
        }
        return binding, live

    def test_tracked_contract_is_valid(self) -> None:
        self.assertEqual([], MODULE.validate(self.contract))

    def test_missing_observation_date_fails_closed(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["sources"][0].pop("observed_at")
        self.assertIn("source limen_exact_head has no observation date", MODULE.validate(changed))

    def test_publication_and_outreach_states_are_rejected(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["status"] = "DONE"
        changed["external_validation"]["status"] = "outreach_started"
        errors = MODULE.validate(changed)
        self.assertIn("status must remain PREPARED/PREFLIGHT", errors)
        self.assertIn("external validation must remain rubric-only/no-outreach", errors)

    def test_preflight_never_counts_as_closure(self) -> None:
        self.assertFalse(self.contract["counts_as_closure"])
        changed = json.loads(json.dumps(self.contract))
        changed["counts_as_closure"] = True
        self.assertIn("counts_as_closure must remain false", MODULE.validate(changed))

    def test_only_w07_remains_unsatisfied(self) -> None:
        progress = self.contract["dependency_progress"]
        self.assertEqual("closed", progress["p02"]["status"])
        self.assertEqual(
            [f"PSP-P03-W0{index}" for index in range(1, 7)],
            progress["c03"]["closed_leaves"],
        )
        self.assertEqual(
            "PSP-P03-W07",
            progress["c03"]["sole_unsatisfied_leaf"]["work_id"],
        )
        self.assertFalse(progress["c03"]["sole_unsatisfied_leaf"]["outbound_from_c04"])
        self.assertEqual(MODULE.P02_ACCEPTED_HEAD, progress["p02"]["exact_head"])
        self.assertEqual(MODULE.C03_CURRENT_HEAD, progress["c03"]["exact_head"])
        self.assertEqual(MODULE.C03_MERGE_COMMIT, progress["c03"]["merge_commit"])
        self.assertEqual(
            MODULE.C03_ACCEPTED_P03_ANCESTOR,
            progress["c03"]["accepted_p03_ancestor"],
        )
        self.assertEqual(0, progress["c03"]["sole_unsatisfied_leaf"]["current_valid_readers"])
        self.assertFalse(progress["c03"]["sole_unsatisfied_leaf"]["synthetic_or_model_readers_allowed"])

    def test_malformed_dependency_progress_fails_closed(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["dependency_progress"] = "not-an-object"
        self.assertIn("dependency_progress must be an object", MODULE.validate(changed))

    def test_c03_source_and_merge_bindings_fail_closed_on_drift(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["dependency_progress"]["c03"]["merge_commit"] = "0" * 40
        c03_source = next(row for row in changed["dependency_sources"] if row["id"] == "c03_identity_offers")
        c03_source["merge_commit"] = "1" * 40
        errors = MODULE.validate(changed)
        self.assertIn("C03 merged integration commit mismatch", errors)
        self.assertIn("C03 dependency source must bind its merged main commit", errors)

    def test_resolver_withholds_all_preflight_claims(self) -> None:
        dependency_rows = MODULE.resolve_dependency_sources(self.contract)
        self.assertTrue(all(row["resolved"] for row in dependency_rows))
        claims = MODULE.resolve_claims(
            self.contract,
            as_of=date(2026, 8, 12),
            dependency_rows=dependency_rows,
        )
        self.assertEqual(3, len(claims))
        self.assertTrue(all(not claim["publishable"] for claim in claims))
        self.assertTrue(all(claim["observation_dates"] for claim in claims))
        self.assertTrue(all("c04_formalization_pending" in claim["reason_codes"] for claim in claims))
        self.assertEqual(
            {"C02-PROOF-LIMEN", "C02-PROOF-PUBLIC-RECORDS", "C02-PROOF-AI-CHAT-EXPORTER"},
            {claim["claim_id"] for claim in claims},
        )

    def test_dependency_resolver_enforces_exact_blob_identity(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["dependency_sources"][0]["expected_blob"] = "0" * 40
        rows = MODULE.resolve_dependency_sources(changed)
        registry = next(row for row in rows if row["source_id"] == "p02_live_registry")
        self.assertFalse(registry["resolved"])
        self.assertEqual("blob_mismatch", registry["reason"])

    def test_upstream_registry_claims_and_offer_bindings_are_exact(self) -> None:
        result = MODULE.verify_upstream_bindings(self.contract)
        self.assertEqual("pass", result["status"])
        self.assertEqual([], result["errors"])
        self.assertEqual(8, len(result["checked"]))
        self.assertTrue(all(row["blob_match"] for row in result["checked"]))

    def test_commercial_set_has_five_generated_offers_and_no_l1_payload(self) -> None:
        artifacts = self.contract["commercial_artifact_set"]["artifacts"]
        self.assertEqual(set(MODULE.EXPECTED_OFFER_BINDINGS), {artifact["id"] for artifact in artifacts})
        self.assertTrue(all("L1" not in artifact["levels"] for artifact in artifacts))
        partnership = next(
            artifact for artifact in artifacts if artifact["id"] == "product_operating_partnership_review"
        )
        self.assertEqual(["L3"], partnership["levels"])
        self.assertFalse(partnership["public_front_door"])

    def test_surface_audit_has_an_explicit_denominator(self) -> None:
        claims = MODULE.discover_material_claims(self.contract)
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        surface_count = len(self.contract["surface_audit_model"]["surfaces"])
        self.assertGreater(len(claims), len(self.contract["flagships"]))
        self.assertEqual(surface_count * len(claims), len(rows))
        self.assertTrue(any("Top 1% Python committer" in claim["candidate_claim"] for claim in claims))
        self.assertTrue(any("314 repositories total" in claim["candidate_claim"] for claim in claims))
        unpublished = next(
            claim for claim in claims if claim["candidate_claim"] == "Cost/reliability/verification metrics"
        )
        self.assertFalse(unpublished["publishable"])
        self.assertEqual("withhold_or_remove", unpublished["action"])
        self.assertFalse(any(claim["candidate_claim"] == "Claim ID" for claim in claims))
        self.assertTrue(all(row["canonical_or_drift"] == "not_audited" for row in rows))

    def test_surface_audit_requires_every_cell_and_private_disproof(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest_rows = []
        for row in rows:
            manifest_rows.append(
                {
                    **row,
                    "presence": "absent",
                    "contains_private_material": False,
                }
            )
        result = MODULE.audit_surface_manifest(self.contract, {"rows": manifest_rows})
        self.assertEqual("pass", result["status"])
        manifest_rows.pop()
        failed = MODULE.audit_surface_manifest(self.contract, {"rows": manifest_rows})
        self.assertEqual("fail", failed["status"])
        self.assertIn("missing surface cells: 1", failed["errors"])

    def test_present_surface_claim_requires_evidence_disclosure_and_action(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest_rows = [{**row, "presence": "absent", "contains_private_material": False} for row in rows]
        present = manifest_rows[0]
        present.update(
            {
                "presence": "present",
                "canonical_or_drift": "canonical",
                "status": "verified",
            }
        )
        present.pop("source_ids")
        present.pop("disclosure_level")
        present.pop("action")
        result = MODULE.audit_surface_manifest(self.contract, {"rows": manifest_rows})
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("present claim missing required evidence fields" in error for error in result["errors"]))

    def test_withheld_canonical_claim_cannot_be_marked_present(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest_rows = [{**row, "presence": "absent", "contains_private_material": False} for row in rows]
        present = next(row for row in manifest_rows if row["action"] == "withhold_or_remove")
        present.update({"presence": "present", "canonical_or_drift": "canonical", "status": "verified"})
        result = MODULE.audit_surface_manifest(self.contract, {"rows": manifest_rows})
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("not eligible for public presence" in error for error in result["errors"]))

    def test_synthetic_architecture_fixture_passes_and_private_keys_fail(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual("pass", MODULE.validate_demo_fixture(self.contract, fixture)["status"])
        fixture["records"][0]["secret"] = "not-allowed"
        self.assertEqual("fail", MODULE.validate_demo_fixture(self.contract, fixture)["status"])

    def test_nested_demo_private_key_fails_closed(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["records"][0]["payload"] = {"nested": [{"apiToken": "not-allowed"}]}
        result = MODULE.validate_demo_fixture(self.contract, fixture)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("apiToken" in error for error in result["errors"]))

    def test_demo_private_values_fail_closed_under_innocent_keys(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        for value in ("customer@example.com", "ghp_abcdefghijklmnopqrstuvwxyz"):
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            fixture["records"][0]["notes"] = value
            result = MODULE.validate_demo_fixture(self.contract, fixture)
            self.assertEqual("fail", result["status"])
            self.assertTrue(any("$.notes" in error for error in result["errors"]))

    def test_demo_password_keys_fail_closed(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        for key in ("password", "passphrase", "pwd"):
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            fixture["records"][0][key] = "synthetic-but-still-forbidden"
            result = MODULE.validate_demo_fixture(self.contract, fixture)
            self.assertEqual("fail", result["status"])
            self.assertTrue(any(f"$.{key}" in error for error in result["errors"]))

    def test_external_validation_requires_two_substantive_independent_objects(self) -> None:
        empty = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": []},
        )
        self.assertEqual("fail", empty["status"])
        required = self.contract["external_validation"]["minimum_fields"]
        placeholders = {
            "outreach_performed": False,
            "objects": [
                {field: None for field in required},
                {field: None for field in required},
            ],
        }
        for row in placeholders["objects"]:
            row["consent status"] = "public_consented"
        result = MODULE.validate_external_objects(self.contract, placeholders)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("empty fields" in error for error in result["errors"]))

    def test_external_validation_rejects_explicit_non_independence(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["independence disclosure"] = "not independent - authored by the subject"
            row["object URL or receipt"] = f"https://example.invalid/object-{index}"
            row["date"] = "2026-08-14"
            row["consent status"] = "public_consented"
            objects.append(row)
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("affirmative independence" in error for error in result["errors"]))

    def test_withdrawn_external_objects_do_not_satisfy_the_minimum(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = f"https://example.invalid/object-{index}"
            row["date"] = "2026-08-14"
            row["consent status"] = "withdrawn"
            objects.append(row)
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(0, result["substantive_public_count"])
        self.assertTrue(any("substantive public-consented objects" in error for error in result["errors"]))

    def test_malformed_public_failure_vocabulary_returns_validation_error(self) -> None:
        for value in (None, [{"unhashable": True}]):
            changed = copy.deepcopy(self.contract)
            changed["cost_failure_reproduction"]["public_failure_classes"] = value
            errors = MODULE.validate(changed)
            self.assertIn(
                "cost/failure reproduction must declare the reviewed public failure vocabulary",
                errors,
            )

    def test_formalization_reports_only_the_genuine_dependency(self) -> None:
        result = MODULE.formalization_readiness(self.contract)
        self.assertFalse(result["ready"])
        self.assertEqual(
            ["PSP-P03-W07 genuine five-reader receipt", "PSP-C03 formal closure predicates"],
            result["residual_gates"],
        )
        self.assertEqual([], result["errors"])

    def test_formalization_cli_exits_nonzero_until_ready(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode", "formalization", "--json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, completed.returncode)
        self.assertEqual("fail", json.loads(completed.stdout)["status"])

    def test_formalization_rejects_fabricated_w07_strings(self) -> None:
        closure = {
            "chunk_id": "PSP-C03",
            "status": "pass",
            "exact_head": MODULE.C03_CURRENT_HEAD,
            "phase_predicates": {"PSP-P03": "pass", "PSP-P04": "pass"},
            "w07_receipt": {
                "work_id": "PSP-P03-W07",
                "issue_url": "https://github.com/organvm/limen/issues/2188",
                "url": "fabricated",
                "sha256": "fabricated",
                "receipt": {},
            },
        }
        result = MODULE.formalization_readiness(
            self.contract,
            closure,
            w07_verification={
                "status": "pass",
                "work_id": "PSP-P03-W07",
                "receipt_url": "https://github.com/organvm/limen/issues/2188#issuecomment-1",
                "receipt_sha256": hashlib.sha256(b"receipt").hexdigest(),
            },
        )
        self.assertFalse(result["ready"])
        self.assertTrue(any("immutable #2188 issue comment" in error for error in result["errors"]))

    def test_w07_receipt_requires_the_exact_tracked_predicate_command(self) -> None:
        binding, live = self._valid_w07_binding()
        self.assertEqual([], MODULE._validate_w07_receipt_binding(binding, ROOT, live))
        receipt = binding["receipt"]
        assert isinstance(receipt, dict)
        predicate = receipt["predicate"]
        assert isinstance(predicate, dict)
        predicate["command"] = "echo validate_p03_w07_blinded_reader.py"
        digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        binding["sha256"] = digest
        live["receipt_sha256"] = digest
        errors = MODULE._validate_w07_receipt_binding(binding, ROOT, live)
        self.assertTrue(any("exact manifest-owned" in error for error in errors))

    def test_program_binding_covers_all_p05_leaves(self) -> None:
        self.assertEqual(
            [f"PSP-P05-W0{index}" for index in range(1, 7)],
            [row["work_id"] for row in self.contract["program_binding"]["leaf_audit"]],
        )


if __name__ == "__main__":
    unittest.main()
