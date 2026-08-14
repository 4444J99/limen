import copy
import contextlib
import importlib.util
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/positioning-proof-preflight.py"
SPEC = importlib.util.spec_from_file_location("positioning_proof_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PositioningProofPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.production_contract = MODULE.load_contract(MODULE.DEFAULT_CONTRACT)
        self.contract = copy.deepcopy(self.production_contract)
        authoritative_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        authority_patch = mock.patch.object(
            MODULE,
            "_canonical_limen_remote_head",
            return_value=("main", authoritative_head),
        )
        authority_patch.start()
        self.addCleanup(authority_patch.stop)
        paths = (
            ".gitignore",
            ".env.example",
            ".env.template",
            ".coderabbit.yaml",
            ".ruff.toml",
            "mise.toml",
        )
        surfaces = self.contract["surface_audit_model"]["surfaces"]
        self.contract["surface_audit_model"]["surface_sources"] = {
            surface: {
                "source_kind": "tracked_blob",
                "source_locator": path,
                "receipt_path": None,
                "extractor": "raw_text_v1",
            }
            for surface, path in zip(surfaces, paths, strict=True)
        }

    def _empty_surface_manifest(self, rows: list[dict[str, object]]) -> dict[str, object]:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        inspections: dict[str, object] = {}
        manifest_rows: list[dict[str, object]] = []
        for surface in self.contract["surface_audit_model"]["surfaces"]:
            inspection_id = f"inspection-{surface}"
            binding = self.contract["surface_audit_model"]["surface_sources"][surface]
            source_locator = binding["source_locator"]
            blob = subprocess.run(
                ["git", "rev-parse", f"{head}:{source_locator}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            content = subprocess.run(
                ["git", "show", f"{head}:{source_locator}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            extracted = MODULE._canonical_surface_extraction(content, binding["extractor"])
            inspections[surface] = {
                "schema_version": MODULE.SURFACE_INSPECTION_SCHEMA,
                "inspection_id": inspection_id,
                "surface": surface,
                "source_kind": binding["source_kind"],
                "source_locator": source_locator,
                "receipt_path": binding["receipt_path"],
                "extractor": binding["extractor"],
                "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "exact_head": head,
                "blob_sha1": blob,
                "raw_response_sha256": None,
                "extracted_text_sha256": hashlib.sha256(extracted).hexdigest(),
                "scanner": MODULE.SURFACE_SCANNER,
                "scanner_version": MODULE.SURFACE_SCANNER_VERSION,
                "matched_claim_ids": [],
            }
        for row in rows:
            manifest_rows.append(
                {
                    **row,
                    "presence": "absent",
                    "contains_private_material": False,
                    "inspection_id": f"inspection-{row['surface']}",
                }
            )
        return {"rows": manifest_rows, "surface_inspections": inspections}

    def _valid_phase_bindings(self) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
        bindings: dict[str, object] = {}
        live: dict[str, dict[str, object]] = {}
        for phase_id, issue_number, digest_character in (
            ("PSP-P03", 2181, "a"),
            ("PSP-P04", 2189, "b"),
        ):
            receipt_url = f"https://github.com/organvm/limen/issues/{issue_number}#issuecomment-1"
            receipt_sha256 = digest_character * 64
            bindings[phase_id] = {
                "receipt_url": receipt_url,
                "receipt_sha256": receipt_sha256,
            }
            live[phase_id] = {
                "status": "pass",
                "phase_id": phase_id,
                "receipt_url": receipt_url,
                "receipt_sha256": receipt_sha256,
                "observed_heads": {"organvm/limen": MODULE.C03_CURRENT_HEAD},
            }
        return bindings, live

    def _passing_w07_payload(self) -> dict[str, object]:
        path = ROOT / "docs/positioning/program/w07_blinded_reader_response_template.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["status"] = "complete"
        payload["collected_at"] = "2026-08-14T16:00:00Z"
        for reader in payload["readers"]:
            reader.update(
                {
                    "role_identified": "A senior production-systems architect with bounded authority.",
                    "buyer_identified": "A named technical or executive sponsor with an active mandate.",
                    "problem_identified": "Delivery lacks decision rights, verification, cost bounds, and handoff.",
                    "proof_identified": "An inspectable governed-delivery system with operating evidence.",
                    "cta_identified": "Discuss the bounded audit or a named senior systems mandate.",
                    "confidence_1_to_5": 5,
                    "element_scores": {"role": True, "buyer": True, "problem": True, "proof": True, "cta": True},
                    "protocol_integrity": {
                        "independent_target_like_reader": True,
                        "genuine_human_response": True,
                        "not_model_or_synthetic": True,
                        "not_author_or_implementation_agent": True,
                        "not_coached": True,
                        "read_once_unprompted": True,
                        "no_facilitator_explanation": True,
                        "no_project_search": True,
                        "contains_no_names_companies_or_contact_data": True,
                    },
                }
            )
        return payload

    def _w07_repository(self, repository: Path, payload: dict[str, object]) -> tuple[str, str]:
        response_path = "docs/receipts/positioning/psp-p03-w07-reader-responses.json"
        memo_path = "docs/receipts/positioning/psp-p03-w07-decision-memo.md"
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "synthetic closure"],
            cwd=repository,
            check=True,
        )
        tracked = (
            MODULE.W07_VALIDATOR_PATH,
            "docs/positioning/program/w07_blinded_reader_response_schema.json",
            "docs/positioning/w07-blinded-reader-protocol.md",
        )
        for path in tracked:
            target = repository / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
        response = repository / response_path
        response.parent.mkdir(parents=True, exist_ok=True)
        response.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        memo = repository / memo_path
        memo.parent.mkdir(parents=True, exist_ok=True)
        try:
            memo_content = MODULE._canonical_w07_decision_memo(payload)
        except ValueError:
            memo_content = b"synthetic invalid-reader decision memo\n"
        memo.write_bytes(memo_content)
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic W07 fixture"],
            cwd=repository,
            check=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return head, response_path

    def _valid_w07_binding(
        self,
        repository: Path,
        head: str,
        response_path: str,
        payload: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        response_digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        memo_path = "docs/receipts/positioning/psp-p03-w07-decision-memo.md"
        memo_digest = hashlib.sha256(
            subprocess.run(
                ["git", "show", f"{head}:{memo_path}"],
                cwd=repository,
                check=True,
                capture_output=True,
            ).stdout
        ).hexdigest()
        receipt = {
            "work_id": "PSP-P03-W07",
            "outcome": "succeeded",
            "observed_heads": {"organvm/limen": head},
            "changed_paths": [response_path, memo_path],
            "evidence_urls": [
                f"https://github.com/organvm/limen/blob/{head}/{response_path}",
                f"https://github.com/organvm/limen/blob/{head}/{memo_path}",
            ],
            "predicate": {
                "command": f"python3 {MODULE.W07_VALIDATOR_PATH} {response_path}",
                "exit_code": 0,
            },
            "reader_evidence": {
                "reader_count": 5,
                "independent_reader_count": 5,
                "synthetic_or_model_reader_count": 0,
                "unresolved_authority_objections": 0,
                "total_score": 25,
                "role_matches": 5,
                "buyer_matches": 5,
                "cta_matches": 5,
                "response_set_path": response_path,
                "response_set_sha256": response_digest,
                "decision_memo_path": memo_path,
                "decision_memo_sha256": memo_digest,
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
        self.assertEqual([], MODULE.validate(self.production_contract))
        self.assertEqual([], MODULE.validate(self.contract))

    def test_surface_source_registry_rejects_reused_contract_identity(self) -> None:
        changed = copy.deepcopy(self.contract)
        sources = changed["surface_audit_model"]["surface_sources"]
        surfaces = changed["surface_audit_model"]["surfaces"]
        sources[surfaces[1]] = copy.deepcopy(sources[surfaces[0]])
        errors = MODULE.validate(changed)
        self.assertTrue(any("reused across canonical surfaces" in error for error in errors))

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
        unsupported = next(
            claim for claim in claims if claim["candidate_claim"] == "`profile-universal-production-claim`"
        )
        self.assertFalse(unsupported["publishable"])
        self.assertEqual("withhold_or_remove", unsupported["action"])
        self.assertFalse(any(claim["candidate_claim"] == "Claim ID" for claim in claims))
        self.assertTrue(all(row["canonical_or_drift"] == "not_audited" for row in rows))

    def test_preflight_ledger_claims_are_not_publishable(self) -> None:
        claims = MODULE.discover_material_claims(self.contract)
        ledger_claims = [claim for claim in claims if "accepted_claims_ledger_inventory" in claim["reason_codes"]]
        self.assertTrue(ledger_claims)
        self.assertTrue(all(not claim["publishable"] for claim in ledger_claims))
        self.assertTrue(all("c04_formalization_pending" in claim["reason_codes"] for claim in ledger_claims))
        self.assertTrue(all(claim["action"] != "audit_canonical_wording" for claim in ledger_claims))

    def test_surface_audit_main_reports_unavailable_claim_inventory_without_traceback(self) -> None:
        stdout = io.StringIO()
        message = "accepted claims-ledger inventory is unavailable or stale"
        argv = [str(SCRIPT), "--mode", "surface-audit", "--json"]
        with (
            mock.patch.object(MODULE, "build_surface_audit_skeleton", side_effect=ValueError(message)),
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = MODULE.main()
        result = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", result["status"])
        self.assertEqual([f"surface audit failed: {message}"], result["errors"])

    def test_all_input_modes_report_malformed_json_without_tracebacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            for mode in ("surface-audit", "demo", "external-validation", "formalization"):
                with self.subTest(mode=mode):
                    stdout = io.StringIO()
                    argv = [str(SCRIPT), "--mode", mode, "--input", str(malformed), "--json"]
                    with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                        exit_code = MODULE.main()
                    result = json.loads(stdout.getvalue())
                    self.assertEqual(1, exit_code)
                    self.assertEqual("fail", result["status"])
                    self.assertTrue(any("failed:" in error for error in result["errors"]))

    def test_surface_audit_requires_every_cell_and_private_disproof(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("pass", result["status"])
        manifest_rows.pop()
        failed = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", failed["status"])
        self.assertIn("missing surface cells: 1", failed["errors"])

    def test_surface_audit_derives_presence_from_bound_inspection_content(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        inspections = manifest["surface_inspections"]
        assert isinstance(manifest_rows, list)
        assert isinstance(inspections, dict)
        manifest_rows[0]["presence"] = "present"
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("row presence differs from the bound inspection" in error for error in result["errors"]))
        surface = manifest_rows[0]["surface"]
        inspection = inspections[surface]
        assert isinstance(inspection, dict)
        inspection["matched_claim_ids"] = [manifest_rows[0]["claim_id"]]
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertTrue(any("matched claims differ from the bound source" in error for error in result["errors"]))

    def test_surface_audit_rejects_wrong_source_path_kind_and_reuse(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        for mutation in ("path", "kind", "reuse"):
            with self.subTest(mutation=mutation):
                manifest = self._empty_surface_manifest(rows)
                inspections = manifest["surface_inspections"]
                assert isinstance(inspections, dict)
                surfaces = list(inspections)
                target = inspections[surfaces[1]]
                assert isinstance(target, dict)
                if mutation == "path":
                    target["source_locator"] = ".gitignore"
                elif mutation == "kind":
                    target["source_kind"] = "live_receipt"
                else:
                    first = inspections[surfaces[0]]
                    assert isinstance(first, dict)
                    for field in ("source_kind", "source_locator", "receipt_path", "extractor"):
                        target[field] = first[field]
                result = MODULE.audit_surface_manifest(self.contract, manifest)
                self.assertEqual("fail", result["status"])
                self.assertTrue(
                    any("contract-owned source binding" in error for error in result["errors"]),
                    result["errors"],
                )

    def test_surface_audit_requires_current_authoritative_head_and_fresh_observation(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        inspections = manifest["surface_inspections"]
        assert isinstance(inspections, dict)
        inspection = next(iter(inspections.values()))
        assert isinstance(inspection, dict)
        inspection["exact_head"] = "f" * 40
        inspection["observed_at"] = "2000-01-01T00:00:00Z"
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("authoritative remote default head" in error for error in result["errors"]))
        self.assertTrue(any("freshness budget" in error for error in result["errors"]))

    def test_surface_scanner_rejects_shortened_inflated_and_contradictory_variants(self) -> None:
        surface = "portfolio_front_door"
        claim_id = "SYNTHETIC-CLAIM"
        canonical = "Four implemented state collectors CA TX FL and NY sit on a broader architecture"
        expected = {(surface, claim_id): {"claim_text": canonical}}
        variants = (
            "Four implemented state collectors CA TX FL and NY establish nationwide completeness",
            "Implemented state collectors CA TX FL NY on a broader architecture",
            "Four implemented state collectors CA TX FL and NY do not sit on a broader architecture",
        )
        for variant in variants:
            with self.subTest(variant=variant):
                matched, drifted = MODULE._surface_claim_scan(variant, expected, surface)
                self.assertEqual([], matched)
                self.assertEqual([claim_id], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            f"The evidence states that {canonical}, with limits documented elsewhere.",
            expected,
            surface,
        )
        self.assertEqual([claim_id], matched)
        self.assertEqual([], drifted)

    def test_visible_surface_extraction_ignores_dynamic_markup_but_not_claim_changes(self) -> None:
        first = b"<html><body><h1>Bounded proof claim</h1><script>nonce='one'</script></body></html>"
        second = b"<html data-nonce='two'><body><h1>Bounded proof claim</h1><script>nonce='two'</script></body></html>"
        changed = b"<html><body><h1>Inflated proof claim</h1><script>nonce='three'</script></body></html>"
        first_extraction = MODULE._canonical_surface_extraction(first, "visible_text_v1")
        second_extraction = MODULE._canonical_surface_extraction(second, "visible_text_v1")
        changed_extraction = MODULE._canonical_surface_extraction(changed, "visible_text_v1")
        self.assertEqual(first_extraction, second_extraction)
        self.assertNotEqual(first_extraction, changed_extraction)

    def test_phase_receipt_comments_require_an_authorized_repository_actor(self) -> None:
        self.assertTrue(
            MODULE._phase_comment_authorized({"user": {"login": "4444J99"}, "author_association": "MEMBER"})
        )
        for comment in (
            {"user": {"login": "outside-user"}, "author_association": "NONE"},
            {"user": {"login": "4444J99"}, "author_association": "NONE"},
            {"author_association": "MEMBER"},
        ):
            with self.subTest(comment=comment):
                self.assertFalse(MODULE._phase_comment_authorized(comment))

    def test_surface_audit_rejects_unhashable_inspection_claim_ids_without_crashing(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        inspections = manifest["surface_inspections"]
        assert isinstance(inspections, dict)
        inspection = next(iter(inspections.values()))
        assert isinstance(inspection, dict)
        inspection["matched_claim_ids"] = [{"claim": "untrusted"}]
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("matched_claim_ids are invalid" in error for error in result["errors"]))

    def test_surface_audit_rejects_unhashable_presence_without_crashing(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        manifest_rows[0]["presence"] = {"state": "present"}
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("surface presence unresolved" in error for error in result["errors"]))

    def test_present_surface_claim_requires_evidence_disclosure_and_action(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        present = manifest_rows[0]
        present.update(
            {
                "presence": "present",
                "canonical_or_drift": "canonical",
            }
        )
        present.pop("source_ids")
        present.pop("disclosure_level")
        present.pop("action")
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("present claim missing required evidence fields" in error for error in result["errors"]))

    def test_present_surface_claim_rejects_drifted_wording(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        present = manifest_rows[0]
        present.update({"presence": "present", "canonical_or_drift": "drift"})
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("differs from canonical wording" in error for error in result["errors"]))

    def test_present_surface_claim_binds_the_exact_canonical_text(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        present = manifest_rows[0]
        present.update(
            {
                "presence": "present",
                "canonical_or_drift": "canonical",
                "claim_text": f"{present['claim_text']} with an inflated implication",
            }
        )
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("claim text differs from canonical inventory" in error for error in result["errors"]))

    def test_present_surface_claim_requires_exact_unique_canonical_sources(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        for suffix in (["unreviewed-extra"], [rows[0]["source_ids"][0]]):
            manifest = self._empty_surface_manifest(rows)
            manifest_rows = manifest["rows"]
            assert isinstance(manifest_rows, list)
            present = manifest_rows[0]
            present.update({"presence": "present", "canonical_or_drift": "canonical"})
            present["source_ids"] = [*present["source_ids"], *suffix]
            result = MODULE.audit_surface_manifest(self.contract, manifest)
            self.assertEqual("fail", result["status"])
            self.assertTrue(
                any(
                    "source ids differ from canonical inventory" in error or "source_ids contain duplicates" in error
                    for error in result["errors"]
                )
            )

    def test_present_surface_claim_binds_exact_iso_observation_dates(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        for invalid in (True, ["not-a-date"], ["2099-01-01"]):
            manifest = self._empty_surface_manifest(rows)
            manifest_rows = manifest["rows"]
            assert isinstance(manifest_rows, list)
            present = manifest_rows[0]
            present.update(
                {
                    "presence": "present",
                    "canonical_or_drift": "canonical",
                    "observed_at": invalid,
                }
            )
            result = MODULE.audit_surface_manifest(self.contract, manifest)
            self.assertEqual("fail", result["status"])
            self.assertTrue(any("observation dates differ" in error for error in result["errors"]))

    def test_withheld_canonical_claim_cannot_be_marked_present(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        present = next(row for row in manifest_rows if row["action"] == "withhold_or_remove")
        present.update({"presence": "present", "canonical_or_drift": "canonical"})
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("not eligible for public presence" in error for error in result["errors"]))

    def test_surface_disclosure_tier_authorizes_placement(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        present = next(
            row
            for row in manifest_rows
            if row["surface"] == "portfolio_front_door" and MODULE._disclosure_floor(row["disclosure_level"]) == 3
        )
        present.update({"presence": "present", "canonical_or_drift": "canonical"})
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("disclosure tier does not authorize" in error for error in result["errors"]))

    def test_present_surface_claim_cannot_promote_canonical_status(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        present = next(row for row in manifest_rows if row["status"] != "verified")
        present.update({"presence": "present", "canonical_or_drift": "canonical", "status": "verified"})
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("status differs from canonical inventory" in error for error in result["errors"]))

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

    def test_demo_unhashable_record_type_fails_closed(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["records"][0]["type"] = {"kind": "run"}
        result = MODULE.validate_demo_fixture(self.contract, fixture)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("nonblank text type" in error for error in result["errors"]))

    def test_demo_requires_the_exact_supported_schema(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        for schema_version in (None, "other.v99"):
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            fixture["schema_version"] = schema_version
            result = MODULE.validate_demo_fixture(self.contract, fixture)
            self.assertEqual("fail", result["status"])
            self.assertTrue(any("schema_version" in error for error in result["errors"]))

    def test_demo_rejects_unknown_root_and_record_fields(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["repository"] = "private-alias"
        fixture["records"][0]["task_body"] = "unreviewed"
        result = MODULE.validate_demo_fixture(self.contract, fixture)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("unknown root fields: repository" in error for error in result["errors"]))
        self.assertTrue(any("unknown packet fields: task_body" in error for error in result["errors"]))

    def test_demo_requires_one_linked_record_for_every_story_stage(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        for record_type, field, invalid_target in (
            ("lease", "packet_id", "missing-packet"),
            ("predicate", "execution_id", "missing-execution"),
            ("recovery", "failure_id", "missing-failure"),
            ("harvest", "receipt_id", "missing-receipt"),
        ):
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            record = next(row for row in fixture["records"] if row["type"] == record_type)
            record[field] = invalid_target
            result = MODULE.validate_demo_fixture(self.contract, fixture)
            self.assertEqual("fail", result["status"])
            self.assertTrue(any(f"must link {field}" in error for error in result["errors"]))

        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["records"].append(dict(fixture["records"][0], id="packet-demo-duplicate"))
        result = MODULE.validate_demo_fixture(self.contract, fixture)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("exactly one packet record" in error for error in result["errors"]))

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
        self.assertTrue(any("nonblank text" in error for error in result["errors"]))

    def test_external_validation_requires_nonblank_text_fields(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = f"https://example.invalid/object-{index}"
            row["date"] = "2026-08-14"
            row["consent status"] = "public_consented"
            objects.append(row)
        objects[0]["method"] = True
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(1, result["substantive_public_count"])
        self.assertTrue(any("method" in error and "nonblank text" in error for error in result["errors"]))

    def test_external_validation_rejects_explicit_non_independence(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
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
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
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

    def test_external_validation_normalizes_receipts_before_deduplication(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index, receipt in enumerate(("https://example.invalid/review", " https://example.invalid/review ")):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = receipt
            row["date"] = "2026-08-14"
            row["consent status"] = "public_consented"
            objects.append(row)
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(1, result["substantive_public_count"])
        self.assertTrue(any("duplicates an existing object receipt" in error for error in result["errors"]))

    def test_future_dated_external_objects_do_not_satisfy_the_minimum(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = f"https://example.invalid/future-{index}"
            row["date"] = "2099-01-01"
            row["consent status"] = "public_consented"
            objects.append(row)
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
            as_of=date(2026, 8, 14),
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(0, result["substantive_public_count"])
        self.assertTrue(any("date cannot be in the future" in error for error in result["errors"]))

    def test_external_validation_requires_contract_approved_object_classes(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = "arbitrary placeholder"
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = f"https://example.invalid/placeholder-{index}"
            row["date"] = "2026-08-14"
            row["consent status"] = "public_consented"
            objects.append(row)
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(0, result["substantive_public_count"])
        self.assertTrue(any("approved object class" in error for error in result["errors"]))

    def test_external_validation_rejects_unhashable_consent_without_crashing(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = f"https://example.invalid/consent-{index}"
            row["date"] = "2026-08-14"
            row["consent status"] = "public_consented"
            objects.append(row)
        objects[0]["consent status"] = {"state": "public_consented"}
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(1, result["substantive_public_count"])
        self.assertTrue(any("public consent disposition" in error for error in result["errors"]))

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
        phase_receipts, phase_verifications = self._valid_phase_bindings()
        closure = {
            "chunk_id": "PSP-C03",
            "status": "pass",
            "exact_head": MODULE.C03_CURRENT_HEAD,
            "phase_predicates": {"PSP-P03": "pass", "PSP-P04": "pass"},
            "phase_receipts": phase_receipts,
            "w07_receipt": {
                "work_id": "PSP-P03-W07",
                "issue_url": "https://github.com/organvm/limen/issues/2188",
                "url": "fabricated",
                "sha256": "fabricated",
                "receipt": {},
            },
        }
        authoritative = {
            "status": "pass",
            "repository": "organvm/limen",
            "closure_head": MODULE.C03_CURRENT_HEAD,
            "default_branch": "main",
            "default_head": MODULE.C03_CURRENT_HEAD,
            "contained": True,
        }
        with mock.patch.object(
            MODULE,
            "_live_authoritative_closure_verification",
            return_value=authoritative,
        ):
            result = MODULE.formalization_readiness(
                self.contract,
                closure,
                w07_verification={
                    "status": "pass",
                    "work_id": "PSP-P03-W07",
                    "receipt_url": "https://github.com/organvm/limen/issues/2188#issuecomment-1",
                    "receipt_sha256": hashlib.sha256(b"receipt").hexdigest(),
                },
                phase_verifications=phase_verifications,
            )
        self.assertFalse(result["ready"])
        self.assertTrue(any("immutable #2188 issue comment" in error for error in result["errors"]))
        self.assertTrue(any("self-declared phase_predicates" in error for error in result["errors"]))

    def test_formalization_uses_the_integrated_c03_main_commit_as_its_ancestry_floor(self) -> None:
        closure = {
            "chunk_id": "PSP-C03",
            "status": "pass",
            "exact_head": MODULE.C03_MERGE_COMMIT,
            "phase_receipts": {},
            "w07_receipt": {},
        }
        remote = {
            "status": "pass",
            "repository": "organvm/limen",
            "closure_head": MODULE.C03_MERGE_COMMIT,
            "default_branch": "main",
            "default_head": MODULE.C03_MERGE_COMMIT,
            "contained": True,
        }
        with mock.patch.object(MODULE, "_live_authoritative_closure_verification", return_value=remote):
            result = MODULE.formalization_readiness(self.contract, closure)
        self.assertFalse(result["ready"])
        self.assertFalse(
            any("final C03 head is not a locally proven descendant" in error for error in result["errors"])
        )

    def test_formalization_rejects_a_closure_head_outside_the_authoritative_default_branch(self) -> None:
        errors = MODULE._validate_authoritative_closure_verification(
            {
                "status": "pass",
                "repository": "organvm/limen",
                "closure_head": MODULE.C03_CURRENT_HEAD,
                "default_branch": "main",
                "default_head": "f" * 40,
                "contained": False,
            },
            MODULE.C03_CURRENT_HEAD,
        )
        self.assertTrue(any("authoritative default branch" in error for error in errors))

    def test_formalization_converts_remote_timeouts_to_a_failed_receipt(self) -> None:
        closure = {
            "chunk_id": "PSP-C03",
            "status": "pass",
            "exact_head": MODULE.C03_MERGE_COMMIT,
            "phase_receipts": {},
            "w07_receipt": {},
        }
        timeout = subprocess.TimeoutExpired(["git", "ls-remote"], 30)
        with mock.patch.object(MODULE, "_live_authoritative_closure_verification", side_effect=timeout):
            result = MODULE.formalization_readiness(self.contract, closure)
        self.assertFalse(result["ready"])
        self.assertTrue(any("timed out" in error for error in result["errors"]))

    def test_live_closure_ancestry_disables_replacement_and_graft_overrides(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "", "")
        injected = {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alternate",
            "GIT_COMMON_DIR": "/tmp/common",
            "GIT_CONFIG_PARAMETERS": "'replace.ref=refs/heads/untrusted'",
            "GIT_DIR": "/tmp/untrusted.git",
            "GIT_INDEX_FILE": "/tmp/index",
            "GIT_NAMESPACE": "untrusted",
            "GIT_OBJECT_DIRECTORY": "/tmp/objects",
            "GIT_SHALLOW_FILE": "/tmp/shallow",
            "GIT_WORK_TREE": "/tmp/tree",
        }
        with (
            mock.patch.dict(MODULE.os.environ, injected, clear=False),
            mock.patch.object(
                MODULE,
                "_canonical_limen_remote_head",
                return_value=("main", MODULE.C03_MERGE_COMMIT),
            ),
            mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run,
        ):
            result = MODULE._live_authoritative_closure_verification(ROOT, MODULE.C03_MERGE_COMMIT)
        self.assertTrue(result["contained"])
        environment = run.call_args.kwargs["env"]
        self.assertEqual("1", environment["GIT_NO_REPLACE_OBJECTS"])
        self.assertEqual(MODULE.os.devnull, environment["GIT_GRAFT_FILE"])
        for key in injected:
            self.assertNotIn(key, environment)

    def test_evidence_git_object_reads_use_the_sanitized_bounded_environment(self) -> None:
        injected = {
            "GIT_DIR": "/tmp/untrusted.git",
            "GIT_OBJECT_DIRECTORY": "/tmp/objects",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alternate",
            "GIT_CONFIG_PARAMETERS": "'replace.ref=refs/heads/untrusted'",
        }
        results = [
            subprocess.CompletedProcess([], 0, "text", ""),
            subprocess.CompletedProcess([], 0, "a" * 40 + "\n", ""),
            subprocess.CompletedProcess([], 0, b"bytes", b""),
            subprocess.CompletedProcess([], 0, "b" * 40 + "\n", ""),
            subprocess.CompletedProcess([], 0, b"receipt", b""),
        ]
        with (
            mock.patch.dict(MODULE.os.environ, injected, clear=False),
            mock.patch.object(MODULE.subprocess, "run", side_effect=results) as run,
        ):
            MODULE._read_git_object(ROOT, "a" * 40, ".gitignore")
            MODULE._read_git_object_bytes(ROOT, "a" * 40, ".gitignore")
            MODULE._git_blob(ROOT, "a" * 40, ".gitignore")
        self.assertEqual(5, run.call_count)
        for call in run.call_args_list:
            self.assertEqual(30, call.kwargs["timeout"])
            environment = call.kwargs["env"]
            self.assertEqual("1", environment["GIT_NO_REPLACE_OBJECTS"])
            for key in injected:
                self.assertNotIn(key, environment)

    def test_live_closure_verification_rejects_an_unpushed_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            fixture = repository / "fixture.txt"
            fixture.write_text("published\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "published"],
                cwd=repository,
                check=True,
            )
            published_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            fixture.write_text("unpublished\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "unpublished"],
                cwd=repository,
                check=True,
            )
            unpublished_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            with mock.patch.object(MODULE, "_canonical_limen_remote_head", return_value=("main", published_head)):
                with self.assertRaisesRegex(ValueError, "authoritative default branch"):
                    MODULE._live_authoritative_closure_verification(repository, unpublished_head)

    def test_phase_receipts_bind_exact_live_marked_receipts(self) -> None:
        bindings, live = self._valid_phase_bindings()
        self.assertEqual(
            [],
            MODULE._validate_phase_receipt_bindings(bindings, ROOT, MODULE.C03_CURRENT_HEAD, live),
        )
        phase = bindings["PSP-P04"]
        assert isinstance(phase, dict)
        phase["receipt_sha256"] = "c" * 64
        errors = MODULE._validate_phase_receipt_bindings(bindings, ROOT, MODULE.C03_CURRENT_HEAD, live)
        self.assertTrue(any("differs from the latest marked live phase receipt" in error for error in errors))

    def test_phase_receipt_observed_heads_must_precede_the_closure_head(self) -> None:
        bindings, live = self._valid_phase_bindings()
        errors = MODULE._validate_phase_receipt_bindings(bindings, ROOT, "0" * 40, live)
        self.assertTrue(any("not an ancestor of the closure head" in error for error in errors))

    def test_w07_receipt_requires_the_exact_tracked_predicate_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            self.assertEqual([], MODULE._validate_w07_receipt_binding(binding, repository, live))
            receipt = binding["receipt"]
            assert isinstance(receipt, dict)
            predicate = receipt["predicate"]
            assert isinstance(predicate, dict)
            predicate["command"] = "echo validate_p03_w07_blinded_reader.py"
            digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            binding["sha256"] = digest
            live["receipt_sha256"] = digest
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
            self.assertTrue(any("exact manifest-owned" in error for error in errors))

    def test_w07_receipt_must_bind_and_revalidate_the_exact_response_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            receipt = binding["receipt"]
            assert isinstance(receipt, dict)
            evidence = receipt["reader_evidence"]
            assert isinstance(evidence, dict)
            evidence["response_set_sha256"] = "b" * 64
            digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            binding["sha256"] = digest
            live["receipt_sha256"] = digest
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
            self.assertTrue(any("exact tracked response blob" in error for error in errors))

            evidence["response_set_sha256"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            ).hexdigest()
            evidence["decision_memo_sha256"] = "d" * 64
            digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            binding["sha256"] = digest
            live["receipt_sha256"] = digest
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
            self.assertTrue(any("exact tracked memo blob" in error for error in errors))

            memo_path = evidence["decision_memo_path"]
            assert isinstance(memo_path, str)
            evidence["decision_memo_sha256"] = hashlib.sha256(
                subprocess.run(
                    ["git", "show", f"{head}:{memo_path}"],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                ).stdout
            ).hexdigest()
            observed_heads = receipt["observed_heads"]
            assert isinstance(observed_heads, dict)
            observed_heads["organvm/limen"] = "a" * 40
            receipt["evidence_urls"] = [
                f"https://github.com/organvm/limen/blob/{'a' * 40}/{response_path}",
                f"https://github.com/organvm/limen/blob/{'a' * 40}/{memo_path}",
            ]
            digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            binding["sha256"] = digest
            live["receipt_sha256"] = digest
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
            self.assertTrue(any("claimed C03 closure head" in error for error in errors))

    def test_w07_receipt_recomputes_the_canonical_decision_memo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            _head, response_path = self._w07_repository(repository, payload)
            memo_path = repository / "docs/receipts/positioning/psp-p03-w07-decision-memo.md"
            memo_path.write_text("synthetic aggregate decision memo\n", encoding="utf-8")
            subprocess.run(["git", "add", str(memo_path)], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "tamper memo"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
            self.assertTrue(any("canonical aggregate" in error for error in errors))

    def test_w07_observed_head_must_be_contained_by_the_closure_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            closure_head = subprocess.run(
                ["git", "rev-parse", f"{head}^"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            errors = MODULE._validate_w07_receipt_binding(
                binding,
                repository,
                live,
                closure_head=closure_head,
            )
            self.assertTrue(any("claimed C03 closure head" in error for error in errors))

    def test_w07_receipt_reexecutes_the_exact_head_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            readers = payload["readers"]
            assert isinstance(readers, list)
            integrity = readers[0]["protocol_integrity"]
            assert isinstance(integrity, dict)
            integrity["genuine_human_response"] = False
            head, response_path = self._w07_repository(repository, payload)
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
            self.assertTrue(any("trusted W07 blinded-reader predicate did not pass" in error for error in errors))

    def test_w07_receipt_does_not_trust_a_validator_from_the_observed_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            readers = payload["readers"]
            assert isinstance(readers, list)
            integrity = readers[0]["protocol_integrity"]
            assert isinstance(integrity, dict)
            integrity["genuine_human_response"] = False
            _, response_path = self._w07_repository(repository, payload)
            validator = repository / MODULE.W07_VALIDATOR_PATH
            validator.write_text(
                "#!/usr/bin/env python3\nprint('PASS: forged observed-head validator')\n"
                "print('SCORE: total=25/25 role=5/5 buyer=5/5 cta=5/5')\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", MODULE.W07_VALIDATOR_PATH], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "forge observed validator"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            errors = MODULE._validate_w07_receipt_binding(
                binding,
                repository,
                live,
                closure_head=head,
            )
            self.assertTrue(any("trusted W07 blinded-reader predicate did not pass" in error for error in errors))

    def test_program_binding_covers_all_p05_leaves(self) -> None:
        self.assertEqual(
            [f"PSP-P05-W0{index}" for index in range(1, 7)],
            [row["work_id"] for row in self.contract["program_binding"]["leaf_audit"]],
        )


if __name__ == "__main__":
    unittest.main()
