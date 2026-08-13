import importlib.util
import json
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
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        surface_count = len(self.contract["surface_audit_model"]["surfaces"])
        self.assertEqual(surface_count * len(self.contract["flagships"]), len(rows))
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

    def test_synthetic_architecture_fixture_passes_and_private_keys_fail(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual("pass", MODULE.validate_demo_fixture(self.contract, fixture)["status"])
        fixture["records"][0]["secret"] = "not-allowed"
        self.assertEqual("fail", MODULE.validate_demo_fixture(self.contract, fixture)["status"])

    def test_formalization_reports_only_the_genuine_dependency(self) -> None:
        result = MODULE.formalization_readiness(self.contract)
        self.assertFalse(result["ready"])
        self.assertEqual(
            ["PSP-P03-W07 genuine five-reader receipt", "PSP-C03 formal closure predicates"],
            result["residual_gates"],
        )
        self.assertEqual([], result["errors"])

    def test_program_binding_covers_all_p05_leaves(self) -> None:
        self.assertEqual(
            [f"PSP-P05-W0{index}" for index in range(1, 7)],
            [row["work_id"] for row in self.contract["program_binding"]["leaf_audit"]],
        )


if __name__ == "__main__":
    unittest.main()
