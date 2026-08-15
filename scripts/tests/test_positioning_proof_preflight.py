import copy
import contextlib
import importlib.util
import hashlib
import io
import json
import os
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
        self.fetch_canonical_limen_objects = MODULE._fetch_canonical_limen_objects
        self.fetch_canonical_limen_bindings = MODULE._fetch_canonical_limen_bindings
        self.canonical_fixture_repositories = [ROOT]

        def local_canonical_objects(
            _default_branch: str,
            default_head: str,
            object_paths: set[str],
        ) -> dict[str, tuple[bytes | None, str | None]]:
            return {path: MODULE._read_git_object_bytes(ROOT, default_head, path) for path in object_paths}

        object_patch = mock.patch.object(
            MODULE,
            "_fetch_canonical_limen_objects",
            side_effect=local_canonical_objects,
        )
        object_patch.start()
        self.addCleanup(object_patch.stop)

        def local_canonical_bindings(
            bindings: set[tuple[str, str]],
            *,
            descendant_head: str | None = None,
        ) -> dict[tuple[str, str], tuple[bytes, str]]:
            resolved: dict[tuple[str, str], tuple[bytes, str]] = {}
            for head, path in bindings:
                source_repository = next(
                    (
                        candidate
                        for candidate in self.canonical_fixture_repositories
                        if subprocess.run(
                            ["git", "cat-file", "-e", f"{head}^{{commit}}"],
                            cwd=candidate,
                            check=False,
                            capture_output=True,
                        ).returncode
                        == 0
                    ),
                    None,
                )
                if source_repository is None:
                    raise ValueError(f"missing local fixture head: {head}")
                if descendant_head is not None:
                    ancestry = subprocess.run(
                        ["git", "merge-base", "--is-ancestor", head, descendant_head],
                        cwd=source_repository,
                        check=False,
                        capture_output=True,
                    )
                    if ancestry.returncode != 0:
                        raise ValueError(f"fixture head is not contained by descendant: {head}")
                content, blob = MODULE._read_git_object_bytes(source_repository, head, path)
                if content is None or blob is None:
                    raise ValueError(f"missing local fixture binding: {head}:{path}")
                resolved[(head, path)] = (content, blob)
            return resolved

        binding_patch = mock.patch.object(
            MODULE,
            "_fetch_canonical_limen_bindings",
            side_effect=local_canonical_bindings,
        )
        self.fetch_canonical_limen_bindings_mock = binding_patch.start()
        self.addCleanup(binding_patch.stop)
        paths = (
            ".gitignore",
            ".ruff.toml",
            "mise.toml",
            "web/worker/package.json",
            "mcp/pyproject.toml",
            "cli/pyproject.toml",
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
            phase_proof_sha256 = ("c" if phase_id == "PSP-P03" else "d") * 64
            phase_proof = {
                "status": "pass",
                "phase_id": phase_id,
                "exit_gate_sha256": "e" * 64,
                "child_receipts_sha256": "f" * 64,
                "child_receipt_evidence": {},
                "remote_state_sha256": "1" * 64,
                "parity_sha256": "2" * 64,
            }
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
                "phase_proof": phase_proof,
                "phase_proof_output_sha256": phase_proof_sha256,
                "phase_proof_predicate": {
                    "command": f"python3 scripts/positioning-program.py --phase-proof {phase_id}",
                    "exit_code": 0,
                    "output_sha256": phase_proof_sha256,
                    "observed_at": "2026-08-14T12:00:00Z",
                },
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
            MODULE.W07_WORKFLOW_PATH,
            MODULE.W07_SCHEMA_PATH,
            MODULE.W07_PROTOCOL_PATH,
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
        if repository not in self.canonical_fixture_repositories:
            self.canonical_fixture_repositories.append(repository)
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
        with tempfile.TemporaryDirectory() as directory:
            response_target = Path(directory) / "w07-reader-responses.json"
            response_target.write_text(json.dumps(payload), encoding="utf-8")
            predicate_result = subprocess.run(
                [sys.executable, str(ROOT / MODULE.W07_VALIDATOR_PATH), str(response_target)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        predicate_output_sha256 = hashlib.sha256(predicate_result.stdout.encode("utf-8")).hexdigest()
        receipt = {
            "schema_version": "limen.positioning_work_receipt.v1",
            "work_id": "PSP-P03-W07",
            "acceptance_sha256": "a" * 64,
            "authority": {
                "kind": "direct_human_session",
                "session_id": "synthetic-test-session",
                "executor": "codex",
                "human_protected": True,
            },
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
                "observed_at": "2026-08-08T12:00:00Z",
                "output_sha256": predicate_output_sha256,
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
            "rollback": {
                "invoked": False,
                "state": "not needed; accepted W03-W06 remains the return path",
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
            "authenticated_receipt": copy.deepcopy(receipt),
        }
        return binding, live

    def test_tracked_contract_is_valid(self) -> None:
        self.assertEqual([], MODULE.validate(self.production_contract))

    def test_malformed_flagship_entries_fail_as_structured_validation_errors(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["flagships"] = [None]
        self.assertIn("flagship must be an object", MODULE.validate(changed))

        changed["flagships"] = None
        self.assertIn("flagships must be a list", MODULE.validate(changed))

    def test_formalization_contract_exact_binds_complete_python_dependency_trees(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["formalization_gate"]["trusted_python_dependencies"]["pyyaml"]["python_source_tree_sha256"] = "0" * 64
        self.assertIn(
            "formalization must exact-bind the complete trusted Python dependency trees",
            MODULE.validate(changed),
        )
        changed = copy.deepcopy(self.contract)
        changed["formalization_gate"]["trusted_python_dependencies"]["w07_jsonschema"]["source_tree_sha256"] = "0" * 64
        self.assertIn(
            "formalization must exact-bind the complete trusted Python dependency trees",
            MODULE.validate(changed),
        )
        self.assertEqual([], MODULE.validate(self.contract))

    def test_external_validation_contract_binds_authenticated_comment_time(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["external_validation"].pop("receipt_time_rule")
        self.assertIn(
            "external validation must bind receipt time to the authenticated comment version",
            MODULE.validate(changed),
        )

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

    def test_non_mapping_dependency_source_fails_closed_without_crashing(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["dependency_sources"].append(None)
        self.assertIn("dependency source must be an object", MODULE.validate(changed))

    def test_c03_source_and_merge_bindings_fail_closed_on_drift(self) -> None:
        accepted = next(row for row in self.contract["dependency_sources"] if row["id"] == "c03_identity_offers")
        self.assertEqual("main", accepted["branch"])
        self.assertEqual(MODULE.C03_MERGE_COMMIT, accepted["exact_head"])
        self.assertEqual(MODULE.C03_MERGE_COMMIT, self.contract["commercial_artifact_set"]["source_head"])
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
        self.assertTrue(any("314 repositories" in claim["candidate_claim"] for claim in claims))
        self.assertFalse(any(claim["candidate_claim"] == "Cost/reliability/verification metrics" for claim in claims))
        self.assertFalse(any(claim["candidate_claim"] == "`profile-universal-production-claim`" for claim in claims))
        self.assertFalse(any(claim["candidate_claim"] == "Claim ID" for claim in claims))
        self.assertTrue(all(row["canonical_or_drift"] == "not_audited" for row in rows))

    def test_preflight_ledger_claims_are_not_publishable(self) -> None:
        claims = MODULE.discover_material_claims(self.contract)
        ledger_claims = [claim for claim in claims if "accepted_claims_ledger_inventory" in claim["reason_codes"]]
        self.assertTrue(ledger_claims)
        self.assertTrue(all(not claim["publishable"] for claim in ledger_claims))
        self.assertTrue(all("c04_formalization_pending" in claim["reason_codes"] for claim in ledger_claims))
        self.assertTrue(all(claim["action"] != "audit_canonical_wording" for claim in ledger_claims))

    def test_ledger_publication_authority_uses_the_exact_status_vocabulary(self) -> None:
        content = """Reconciled 2026-08-15
## 1. Claims
| Claim | Status | Evidence / method | Public-safe wording | Tier |
|---|---|---|---|---|
| Independently proven claim | `verified` | receipt | As independently proven. | L1 |
| Verified raw wording | `verified` | receipt | as-is | L2 |
| Reviewed derived claim | `derived-reviewed` | receipt | Reviewed derived wording. | L2 |
| Unreviewed derived claim | `derived` | calculation | Decorative wording. | L2 |
| Repository assertion | `repository-asserted` | README only | repository-reported until a receipt exists | L2 with label |
| Unknown status | `invented` | none | polished but unauthorized wording | L1 |

## 7. Metrics
| Metric | Status | Evidence |
|---|---|---|
| Three-column metric | `verified` | source |

## 9. Research
| Claim ID | Measurement | Inference | Implication | Prominence | Publishable status |
|---|---|---|---|---|---|
| `research-row` | `verified` | `bounded` | `not_established` | `retain_l1` | `provisional_verified_wording` |
"""
        claims = MODULE._ledger_material_claims(
            content,
            "ledger",
            formalization_pending=False,
            claim_policy=self.contract["claim_policy"],
        )
        by_text = {claim["candidate_claim"]: claim for claim in claims}
        self.assertEqual("audit_canonical_wording", by_text["As independently proven."]["action"])
        self.assertEqual("audit_canonical_wording", by_text["Verified raw wording"]["action"])
        self.assertEqual("audit_canonical_wording", by_text["Reviewed derived wording."]["action"])
        self.assertEqual("withhold_or_remove", by_text["Unreviewed derived claim"]["action"])
        self.assertEqual("withhold_or_remove", by_text["Repository assertion"]["action"])
        self.assertEqual("withhold_or_remove", by_text["Unknown status"]["action"])
        self.assertNotIn("Three-column metric", by_text)
        self.assertNotIn("`research-row`", by_text)

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

    def test_validate_mode_reuses_one_authenticated_canonical_object_snapshot(self) -> None:
        stdout = io.StringIO()
        MODULE._fetch_canonical_limen_bindings.reset_mock()
        argv = [str(SCRIPT), "--mode", "validate", "--json"]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            exit_code = MODULE.main()
        result = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code, result)
        self.assertEqual("pass", result["status"])
        MODULE._fetch_canonical_limen_bindings.assert_called_once()
        requested = MODULE._fetch_canonical_limen_bindings.call_args.args[0]
        self.assertEqual(MODULE._contract_canonical_binding_request(self.production_contract), requested)

    def test_preflight_main_reports_bounded_subprocess_timeout_without_traceback(self) -> None:
        stdout = io.StringIO()
        timeout = subprocess.TimeoutExpired(["git", "show"], 30)
        argv = [str(SCRIPT), "--mode", "resolve", "--json"]
        with (
            mock.patch.object(MODULE, "resolve_dependency_sources", side_effect=timeout),
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = MODULE.main()
        result = json.loads(stdout.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("timed out" in error for error in result["errors"]))

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

    def test_all_input_modes_reject_duplicate_json_members_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"reason":"person@example.invalid","reason":"synthetic"}', encoding="utf-8")
            for mode in ("surface-audit", "demo", "external-validation", "formalization"):
                with self.subTest(mode=mode):
                    stdout = io.StringIO()
                    argv = [str(SCRIPT), "--mode", mode, "--input", str(duplicate), "--json"]
                    with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                        exit_code = MODULE.main()
                    result = json.loads(stdout.getvalue())
                    self.assertEqual(1, exit_code)
                    self.assertEqual("fail", result["status"])
                    self.assertTrue(any("duplicate JSON member: reason" in error for error in result["errors"]))

            unsafe_duplicate = Path(directory) / "unsafe-duplicate.json"
            unsafe_value = "password: hunter2alpha"  # allow-secret: synthetic adversarial fixture
            unsafe_duplicate.write_text(
                json.dumps({unsafe_value: "first"})[:-1] + f',{json.dumps(unsafe_value)}:"second"}}',
                encoding="utf-8",
            )
            stdout = io.StringIO()
            argv = [str(SCRIPT), "--mode", "demo", "--input", str(unsafe_duplicate), "--json"]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                exit_code = MODULE.main()
            serialized = stdout.getvalue()
            result = json.loads(serialized)
            self.assertEqual(1, exit_code)
            self.assertEqual("fail", result["status"])
            self.assertNotIn("hunter2alpha", serialized)
            self.assertEqual(
                ["demo failed: input rejected by public-safety validation"],
                result["errors"],
            )

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

    def test_surface_audit_rejects_an_empty_self_consistent_denominator(self) -> None:
        changed = copy.deepcopy(self.contract)
        changed["surface_audit_model"]["surfaces"] = []
        changed["surface_audit_model"]["surface_sources"] = {}
        changed["surface_audit_model"]["surface_levels"] = {}
        validation_errors = MODULE.validate(changed)
        self.assertTrue(any("canonical surface denominator" in error for error in validation_errors))
        result = MODULE.audit_surface_manifest(
            changed,
            {"rows": [], "surface_inspections": {}},
        )
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("canonical surface denominator" in error for error in result["errors"]))

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

    def test_surface_audit_derives_private_material_from_bound_content(self) -> None:
        for telephone in (
            "+1 (212) 555-1234",
            "212-555-1234",
            "+44 20 7946 0958",
            "tel:+12125551234",
            "phone: 2125551234",
            "Phone No: 2125551234",
            "Mobile #: 2125551234",
            "Contact No. 2125551234",
            "telephone number is 12125551234",
            "contact number 12125551234",
        ):
            with self.subTest(telephone=telephone):
                self.assertTrue(MODULE._surface_contains_private_material(f"Call {telephone} for access"))
        for public_number in (
            "Observed 2026-08-15 with 127 objects",
            "Python 3.13.2",
            "address 192.168.100.100",
            "issue 1234567890",
            "sha256 " + "a" * 64,
        ):
            with self.subTest(public_number=public_number):
                self.assertFalse(MODULE._surface_contains_private_material(public_number))
        surface = self.contract["surface_audit_model"]["surfaces"][0]
        self.contract["surface_audit_model"]["surfaces"] = [surface]
        self.contract["surface_audit_model"]["surface_sources"] = {
            surface: {
                "source_kind": "tracked_blob",
                "source_locator": ".gitignore",
                "receipt_path": None,
                "extractor": "raw_text_v1",
            }
        }
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        inspections = manifest["surface_inspections"]
        assert isinstance(inspections, dict)
        inspection = inspections[surface]
        assert isinstance(inspection, dict)
        private_content = b"support contact: customer@example.com\n"
        extraction = MODULE._canonical_surface_extraction(private_content, "raw_text_v1")
        inspection["extracted_text_sha256"] = hashlib.sha256(extraction).hexdigest()
        read_git_object_bytes = MODULE._read_git_object_bytes

        def inspected_surface_only(repository: Path, head: str, path: str) -> tuple[bytes | None, str | None]:
            if path == ".gitignore":
                return private_content, inspection["blob_sha1"]
            return read_git_object_bytes(repository, head, path)

        with (
            mock.patch.object(
                MODULE,
                "EXPECTED_SURFACE_LEVELS",
                {surface: self.contract["surface_audit_model"]["surface_levels"][surface]},
            ),
            mock.patch.object(
                MODULE,
                "_read_git_object_bytes",
                side_effect=inspected_surface_only,
            ),
        ):
            result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("private material in the bound source" in error for error in result["errors"]))
        self.assertTrue(
            any("private-material disposition differs from the bound inspection" in error for error in result["errors"])
        )

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

    def test_surface_audit_fails_closed_when_isolated_authority_fetch_times_out(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        timeout = subprocess.TimeoutExpired(["git", "fetch"], 120)
        with mock.patch.object(MODULE, "_fetch_canonical_limen_objects", side_effect=timeout):
            result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(
            any("canonical surface inspection objects are unavailable" in error for error in result["errors"])
        )

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

        short_expected = {(surface, "SHORT-CLAIM"): {"claim_text": "Zero external human contributors"}}
        matched, drifted = MODULE._surface_claim_scan(
            "One hundred external human contributors",
            short_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["SHORT-CLAIM"], drifted)

        ranked_expected = {(surface, "RANKED-CLAIM"): {"claim_text": "Top 1% Python committer"}}
        matched, drifted = MODULE._surface_claim_scan(
            "Top 2% Python committer",
            ranked_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["RANKED-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "Not Top 1% Python committer",
            ranked_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["RANKED-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "Top 1% Python committer is false",
            ranked_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["RANKED-CLAIM"], drifted)

        long_canonical = "Limen demonstrates governed multi-agent delivery with durable exact-head receipts"
        long_expected = {(surface, "LONG-CLAIM"): {"claim_text": long_canonical}}
        matched, drifted = MODULE._surface_claim_scan(
            "Limen fabricates governed multi-agent delivery with durable exact-head receipts",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "Limen demonstrates governed; multi-agent delivery with durable exact-head receipts.",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        block_split = MODULE._canonical_surface_extraction(
            b"<p>Limen demonstrates governed</p><p>multi-agent delivery with durable exact-head receipts</p>",
            "visible_text_v3",
        ).decode("utf-8")
        matched, drifted = MODULE._surface_claim_scan(block_split, long_expected, surface)
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        address_split = MODULE._canonical_surface_extraction(
            b"<address>Limen demonstrates governed</address>"
            b"<address>multi-agent delivery with durable exact-head receipts</address>",
            "visible_text_v3",
        ).decode("utf-8")
        matched, drifted = MODULE._surface_claim_scan(address_split, long_expected, surface)
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "Limen fabricates governed distributed agent delivery using durable exact commit receipts",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "A deliberately padded public paragraph introduces unrelated architecture, delivery, "
            "and governance context before stating that Limen fabricates governed distributed agent "
            "delivery using durable exact commit receipts amid several additional explanatory clauses "
            "about bounded verification, documentation, and operational limits.",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        for separator in ("\u200d", "\u034f", "\ufe0f"):
            with self.subTest(default_ignorable=hex(ord(separator))):
                format_obfuscated = separator.join(long_canonical)
                matched, drifted = MODULE._surface_claim_scan(format_obfuscated, long_expected, surface)
                self.assertEqual(["LONG-CLAIM"], matched)
                self.assertEqual([], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "There is no evidence supporting the statement that Limen demonstrates governed "
            "multi-agent delivery with durable exact-head receipts.",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        for framing in (
            "It is false that Limen demonstrates governed multi-agent delivery with durable exact-head receipts.",
            "It is not the case that Limen demonstrates governed multi-agent delivery with durable exact-head "
            "receipts.",
            "We cannot truthfully say that Limen demonstrates governed multi-agent delivery with durable "
            "exact-head receipts.",
        ):
            with self.subTest(framing=framing):
                matched, drifted = MODULE._surface_claim_scan(framing, long_expected, surface)
                self.assertEqual([], matched)
                self.assertEqual(["LONG-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "There is no evidence for an unrelated adoption claim. "
            "Limen demonstrates governed multi-agent delivery with durable exact-head receipts.",
            long_expected,
            surface,
        )
        self.assertEqual(["LONG-CLAIM"], matched)
        self.assertEqual([], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "Limen demonstrates governed. Multi-agent delivery with durable exact-head receipts.",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "Unlike products that are not open source, Limen demonstrates governed multi-agent "
            "delivery with durable exact-head receipts.",
            long_expected,
            surface,
        )
        self.assertEqual(["LONG-CLAIM"], matched)
        self.assertEqual([], drifted)

        matched, drifted = MODULE._surface_claim_scan(
            "There is no evidence supporting the statement that Limen demonstrates governed "
            "multi-agent delivery with durable exact-head receipts. Later evidence confirms that "
            "Limen demonstrates governed multi-agent delivery with durable exact-head receipts.",
            long_expected,
            surface,
        )
        self.assertEqual([], matched)
        self.assertEqual(["LONG-CLAIM"], drifted)

    def test_visible_surface_extraction_ignores_dynamic_markup_but_not_claim_changes(self) -> None:
        first = b"<html data-nonce='one'><body><h1>Bounded proof claim</h1></body></html>"
        second = b"<html data-nonce='two'><body><h1>Bounded proof claim</h1></body></html>"
        changed = b"<html data-nonce='three'><body><h1>Inflated proof claim</h1></body></html>"
        first_extraction = MODULE._canonical_surface_extraction(first, "visible_text_v3")
        second_extraction = MODULE._canonical_surface_extraction(second, "visible_text_v3")
        changed_extraction = MODULE._canonical_surface_extraction(changed, "visible_text_v3")
        self.assertEqual(first_extraction, second_extraction)
        self.assertNotEqual(first_extraction, changed_extraction)
        for hidden_tag in ("style", "template", "noscript"):
            with self.subTest(hidden_tag=hidden_tag):
                with self.assertRaisesRegex(ValueError, "unterminated hidden"):
                    MODULE._canonical_surface_extraction(
                        f"<html><body>Bounded proof claim<{hidden_tag}>hidden inflated proof claim".encode(),
                        "visible_text_v3",
                    )
        metadata_only = MODULE._canonical_surface_extraction(
            b"<html><head><title>Metadata proof claim</title></head><body>Visible proof</body></html>",
            "visible_text_v3",
        )
        self.assertEqual(b"Visible proof\n", metadata_only)
        for malformed_head in (
            "<html><head><div>Browser-visible proof claim</div></head></html>",
            "<html><head>Browser-visible proof claim</head></html>",
        ):
            with self.subTest(malformed_head=malformed_head):
                with self.assertRaisesRegex(ValueError, "head-closing rules"):
                    MODULE._canonical_surface_extraction(malformed_head.encode(), "visible_text_v3")
        for executable_markup in (
            "<script>document.body.hidden=true</script><p>Claim</p>",
            "<script src='/visibility.js'></script><p>Claim</p>",
            "<p onclick='this.hidden=true'>Claim</p>",
            "<p ONLOAD='this.hidden=true'>Claim</p>",
            "<a href='javascript:this.hidden=true'>Claim</a>",
            "<iframe src='/visibility.html'>Claim</iframe>",
            "<frameset><frame src='/visibility.html'></frameset>",
            "<FRAME src='/visibility.html'/>",
        ):
            with self.subTest(executable_markup=executable_markup):
                with self.assertRaisesRegex(ValueError, "executable"):
                    MODULE._canonical_surface_extraction(executable_markup.encode(), "visible_text_v3")
        for svg_markup in (
            "<svg><text>Browser-visible proof claim</text></svg>",
            "<SVG><text>Browser-visible proof claim</text></SVG>",
        ):
            with self.subTest(svg_markup=svg_markup):
                with self.assertRaisesRegex(ValueError, "active-content"):
                    MODULE._canonical_surface_extraction(svg_markup.encode(), "visible_text_v3")
        for hidden_markup in (
            "<div hidden>hidden@example.invalid</div>",
            "<aside style='display: none !important'>hidden@example.invalid</aside>",
            "<p style='visibility:hidden'>hidden@example.invalid</p>",
            "<dialog>hidden@example.invalid</dialog>",
            "<details>hidden@example.invalid</details>",
            "<datalist><option>hidden@example.invalid</option></datalist>",
            "<div popover>hidden@example.invalid</div>",
        ):
            with self.subTest(hidden_markup=hidden_markup):
                extraction = MODULE._canonical_surface_extraction(
                    f"<html><body>{hidden_markup}<p>Visible proof</p></body></html>".encode(),
                    "visible_text_v3",
                )
                self.assertEqual(b"Visible proof\n", extraction)
        aria_visible = MODULE._canonical_surface_extraction(
            b"<section aria-hidden='true'>Sighted-user proof claim</section><p>Visible proof</p>",
            "visible_text_v3",
        )
        self.assertIn(b"Sighted-user proof claim", aria_visible)
        open_dialog = MODULE._canonical_surface_extraction(
            b"<dialog open='false'>Visible dialog proof</dialog><details open>Visible details proof</details>",
            "visible_text_v3",
        )
        self.assertEqual(b"Visible dialog proof\nVisible details proof\n", open_dialog)
        for control_markup in (
            "<select><option>Canonical claim</option><option selected>Other</option></select>",
            "<select><option>Canonical claim</option><option>Other</option></select>",
            "<select multiple><option>Canonical claim</option><option selected>Other</option></select>",
            "<select size='2'><option>Canonical claim</option><option>Other</option></select>",
            "<select/>",
            "<canvas>Canonical claim</canvas>",
            "<CANVAS>Canonical claim</CANVAS>",
            "<canvas/>",
            "<img src='/missing' alt='Canonical claim'>",
            "<image src='/missing' alt='Canonical claim'>",
            "<picture><source srcset='/proof.webp'><img src='/proof.png' alt='Canonical claim'></picture>",
            "<noembed>Canonical claim</noembed>",
            "<noframes>Canonical claim</noframes>",
            "<ruby>x<rp>Canonical claim</rp><rt>reading</rt></ruby>",
            "<audio>Canonical claim</audio>",
            "<video>Canonical claim</video>",
            "<meter value='1'>Canonical claim</meter>",
            "<progress value='1'>Canonical claim</progress>",
            "<input value='Canonical claim'>",
            "<input type='button' value='Canonical claim'>",
            "<input placeholder='Canonical claim'>",
            "<textarea placeholder='Canonical claim'></textarea>",
            "<textarea>Canonical claim</textarea>",
        ):
            with self.subTest(control_markup=control_markup):
                with self.assertRaisesRegex(ValueError, "user-agent control"):
                    MODULE._canonical_surface_extraction(control_markup.encode(), "visible_text_v3")
        for shadow_markup in (
            "<div><template shadowrootmode='open'><p>Canonical claim</p></template></div>",
            "<div><template SHADOWROOTMODE='closed'><p>Canonical claim</p></template></div>",
        ):
            with self.subTest(shadow_markup=shadow_markup):
                with self.assertRaisesRegex(ValueError, "declarative shadow DOM"):
                    MODULE._canonical_surface_extraction(shadow_markup.encode(), "visible_text_v3")
        with self.assertRaisesRegex(ValueError, "named-details exclusivity"):
            MODULE._canonical_surface_extraction(
                b"<details name='proof' open><summary>One</summary>Canonical claim</details>",
                "visible_text_v3",
            )
        with self.assertRaisesRegex(ValueError, "implied paragraph-closing rules"):
            MODULE._canonical_surface_extraction(
                b"<p hidden><div>Browser-visible canonical claim</div></p>",
                "visible_text_v3",
            )
        for paragraph_closer in ("center", "dd", "details", "dt", "figure", "li", "search"):
            with self.subTest(paragraph_closer=paragraph_closer):
                with self.assertRaisesRegex(ValueError, "implied paragraph-closing rules"):
                    MODULE._canonical_surface_extraction(
                        f"<p hidden><{paragraph_closer}>Browser-visible canonical claim</{paragraph_closer}></p>".encode(),
                        "visible_text_v3",
                    )
        for legacy_block in ("listing", "marquee", "plaintext", "xmp"):
            with self.subTest(legacy_block=legacy_block):
                with self.assertRaisesRegex(ValueError, "legacy block parsing"):
                    MODULE._canonical_surface_extraction(
                        f"<{legacy_block}>Canonical claim</{legacy_block}>".encode(),
                        "visible_text_v3",
                    )
        legend_split = MODULE._canonical_surface_extraction(
            b"<fieldset><legend>Limen demonstrates governed</legend><p>multi-agent delivery</p></fieldset>",
            "visible_text_v3",
        ).decode("utf-8")
        legend_matched, _legend_drifted = MODULE._surface_claim_scan(
            legend_split,
            {
                ("portfolio_front_door", "CLAIM-LEGEND"): {
                    "claim_text": "Limen demonstrates governed multi-agent delivery"
                }
            },
            "portfolio_front_door",
        )
        self.assertEqual([], legend_matched)
        with self.assertRaisesRegex(ValueError, "table foster-parenting rules"):
            MODULE._canonical_surface_extraction(
                b"<table hidden>Browser-visible canonical claim</table>",
                "visible_text_v3",
            )
        with self.assertRaisesRegex(ValueError, "table foster-parenting rules"):
            MODULE._canonical_surface_extraction(
                b"<table hidden><div>Browser-visible canonical claim</div></table>",
                "visible_text_v3",
            )
        hidden_table_cell = MODULE._canonical_surface_extraction(
            b"<table hidden><tbody><tr><td>Hidden canonical claim</td></tr></tbody></table>",
            "visible_text_v3",
        )
        self.assertEqual(b"\n", hidden_table_cell)
        inline_adjacency = MODULE._canonical_surface_extraction(
            b"<p>Li<span></span>men demonstrates governed multi-agent delivery with durable exact-head receipts</p>",
            "visible_text_v3",
        ).decode("utf-8")
        inline_expected = {
            ("portfolio_front_door", "INLINE-CLAIM"): {
                "claim_text": "Limen demonstrates governed multi-agent delivery with durable exact-head receipts"
            }
        }
        matched, drifted = MODULE._surface_claim_scan(
            inline_adjacency,
            inline_expected,
            "portfolio_front_door",
        )
        self.assertEqual(["INLINE-CLAIM"], matched)
        self.assertEqual([], drifted)
        for bidi_markup in (
            '<bdo dir="rtl">Canonical claim</bdo>',
            "<bdi>Canonical claim</bdi>",
            '<span dir="rtl">Canonical claim</span>',
        ):
            with self.subTest(bidi_markup=bidi_markup):
                with self.assertRaisesRegex(ValueError, "bidirectional rendering evaluation"):
                    MODULE._canonical_surface_extraction(bidi_markup.encode(), "visible_text_v3")
        for legacy_presentation in (
            '<body bgcolor="white"><font color="white">Canonical claim</font></body>',
            '<FONT COLOR="white">Canonical claim</FONT>',
        ):
            with self.subTest(legacy_presentation=legacy_presentation):
                with self.assertRaisesRegex(ValueError, "legacy presentation-attribute evaluation"):
                    MODULE._canonical_surface_extraction(legacy_presentation.encode(), "visible_text_v3")
        for math_markup in (
            "<math><semantics><mi>x</mi><annotation>Canonical claim</annotation></semantics></math>",
            "<MATH/>",
        ):
            with self.subTest(math_markup=math_markup):
                with self.assertRaisesRegex(ValueError, "MathML"):
                    MODULE._canonical_surface_extraction(math_markup.encode(), "visible_text_v3")
        for refresh_markup in (
            "<meta http-equiv='refresh' content='0;url=/other'><p>Canonical claim</p>",
            "<meta HTTP-EQUIV=' Refresh ' content='0;url=/other'/><p>Canonical claim</p>",
        ):
            with self.subTest(refresh_markup=refresh_markup):
                with self.assertRaisesRegex(ValueError, "client-side redirect"):
                    MODULE._canonical_surface_extraction(refresh_markup.encode(), "visible_text_v3")
        encoded_once = MODULE._canonical_surface_extraction(
            b"<p>&amp;#76;imen demonstrates governed multi-agent delivery</p>",
            "visible_text_v3",
        ).decode("utf-8")
        matched, _drifted = MODULE._surface_claim_scan(
            encoded_once,
            {
                ("portfolio_front_door", "CLAIM-ENTITY"): {
                    "claim_text": "Limen demonstrates governed multi-agent delivery"
                }
            },
            "portfolio_front_door",
        )
        self.assertEqual([], matched)
        escaped_visible = MODULE._canonical_surface_extraction(
            b"<p>Limen &lt;unverified&gt; demonstrates governed multi-agent delivery</p>",
            "visible_text_v3",
        ).decode("utf-8")
        escaped_matched, _escaped_drifted = MODULE._surface_claim_scan(
            escaped_visible,
            {
                ("portfolio_front_door", "CLAIM-ANGLE"): {
                    "claim_text": "Limen demonstrates governed multi-agent delivery"
                }
            },
            "portfolio_front_door",
        )
        self.assertEqual([], escaped_matched)
        closed_details = MODULE._canonical_surface_extraction(
            b"<details><summary>Visible summary proof</summary><p>Hidden body proof</p></details>",
            "visible_text_v3",
        )
        self.assertIn(b"Visible summary proof", closed_details)
        self.assertNotIn(b"Hidden body proof", closed_details)
        with self.assertRaisesRegex(ValueError, "table parsing ambiguity"):
            MODULE._canonical_surface_extraction(
                b"<details><table><summary>Browser-visible proof</summary></table></details>",
                "visible_text_v3",
            )
        with self.assertRaisesRegex(ValueError, "unsupported inline style"):
            MODULE._canonical_surface_extraction(
                b"<div style='content-visibility:hidden'>Hidden proof claim</div>",
                "visible_text_v3",
            )
        for malformed in (
            "<div style='display:block' style='display:none'>hidden</div>",
            "<div style='display/**/:none'>hidden</div>",
            r"<div style='d\69splay:none'>hidden</div>",
            "<link rel='stylesheet' rel='alternate' href='/dynamic.css'>",
            "<link REL='alternate' rel='stylesheet' href='/dynamic.css'>",
            "<dialog open open>ambiguous dialog proof</dialog>",
            "<div popover popover>ambiguous popover proof</div>",
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(ValueError, "visibility"):
                    MODULE._canonical_surface_extraction(malformed.encode(), "visible_text_v3")
        with self.assertRaisesRegex(ValueError, "self-closes a non-void"):
            MODULE._canonical_surface_extraction(b"<div hidden/>", "visible_text_v3")
        for stylesheet_markup in (
            "<style>.proof{display:none}</style><div class='proof'>Hidden proof claim</div>",
            "<link rel='stylesheet' href='/dynamic.css'><div>Unverified proof claim</div>",
            "<link rel='alternate stylesheet' href='/dynamic.css'/><div>Unverified proof claim</div>",
        ):
            with self.subTest(stylesheet_markup=stylesheet_markup):
                with self.assertRaisesRegex(ValueError, "stylesheet evaluation"):
                    MODULE._canonical_surface_extraction(stylesheet_markup.encode(), "visible_text_v3")
        with self.assertRaisesRegex(ValueError, "unsupported canonical extractor"):
            MODULE._canonical_surface_extraction(first, "visible_text_v1")

    def test_live_surface_fetch_uses_contract_owned_https_transport(self) -> None:
        source_url = "https://example.com/public-proof"
        response = mock.MagicMock()
        response.geturl.return_value = source_url
        response.read.return_value = b"bounded public proof"
        response.headers.get_all.side_effect = lambda name: (
            ["text/html; charset=utf-8"]
            if name == "Content-Type"
            else ["inline"]
            if name == "Content-Disposition"
            else None
        )
        response.__enter__.return_value = response
        with mock.patch.dict(
            os.environ,
            {"HTTPS_PROXY": "http://proxy.invalid", "SSL_CERT_FILE": "/tmp/untrusted.pem"},
            clear=False,
        ):
            with mock.patch.object(MODULE, "_contract_https_open", return_value=response) as opener:
                content = MODULE._fetch_bounded_public_surface(source_url)
        self.assertEqual(b"bounded public proof", content)
        request = opener.call_args.args[0]
        self.assertEqual(source_url, request.full_url)
        self.assertEqual(30, opener.call_args.kwargs["timeout"])
        self.assertEqual("text/html", request.headers["Accept"])

        for content_types in (
            ["text/plain"],
            ["application/xhtml+xml"],
            ["text/html", "text/plain"],
            ["text/html"],
            ["text/html; charset=utf-16"],
            ["text/html; charset=utf-8; charset=utf-8"],
        ):
            with self.subTest(content_types=content_types):
                response.headers.get_all.side_effect = lambda name, values=content_types: (
                    values if name == "Content-Type" else None
                )
                with mock.patch.object(MODULE, "_contract_https_open", return_value=response):
                    with self.assertRaisesRegex(ValueError, "not HTML"):
                        MODULE._fetch_bounded_public_surface(source_url)

        response.headers.get_all.side_effect = lambda name: (
            ["text/html; charset=utf-8"] if name == "Content-Type" else ["0; url=/other"]
        )
        with mock.patch.object(MODULE, "_contract_https_open", return_value=response):
            with self.assertRaisesRegex(ValueError, "client-side redirect"):
                MODULE._fetch_bounded_public_surface(source_url)

        for dispositions in (
            ["attachment; filename=proof.html"],
            ["inline", "attachment"],
            ["form-data"],
        ):
            with self.subTest(dispositions=dispositions):
                response.headers.get_all.side_effect = lambda name, values=dispositions: (
                    ["text/html; charset=utf-8"]
                    if name == "Content-Type"
                    else values
                    if name == "Content-Disposition"
                    else None
                )
                with mock.patch.object(MODULE, "_contract_https_open", return_value=response):
                    with self.assertRaisesRegex(ValueError, "attachment"):
                        MODULE._fetch_bounded_public_surface(source_url)

    def test_live_surface_inspection_reproduces_canonical_text_not_volatile_raw_html(self) -> None:
        surface = "portfolio_front_door"
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        receipt_content = b"Bounded proof claim\n"
        live_content = b"<html><body>Bounded proof claim</body></html>"
        self.contract["surface_audit_model"]["surfaces"] = [surface]
        self.contract["surface_audit_model"]["surface_sources"] = {
            surface: {
                "source_kind": "live_receipt",
                "source_locator": "https://example.com/public-proof",
                "receipt_path": "docs/receipts/positioning/surface-inspections/public-proof.txt",
                "extractor": "visible_text_v3",
            }
        }
        inspection = {
            "schema_version": MODULE.SURFACE_INSPECTION_SCHEMA,
            "inspection_id": "inspection-public-proof",
            "surface": surface,
            "source_kind": "live_receipt",
            "source_locator": "https://example.com/public-proof",
            "receipt_path": "docs/receipts/positioning/surface-inspections/public-proof.txt",
            "extractor": "visible_text_v3",
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "exact_head": head,
            "blob_sha1": "a" * 40,
            "extracted_text_sha256": hashlib.sha256(receipt_content).hexdigest(),
            "scanner": MODULE.SURFACE_SCANNER,
            "scanner_version": MODULE.SURFACE_SCANNER_VERSION,
            "matched_claim_ids": [],
        }
        with (
            mock.patch.object(
                MODULE,
                "EXPECTED_SURFACE_LEVELS",
                {surface: self.contract["surface_audit_model"]["surface_levels"][surface]},
            ),
            mock.patch.object(
                MODULE,
                "_read_git_object_bytes",
                return_value=(receipt_content, "a" * 40),
            ),
        ):
            with mock.patch.object(MODULE, "_fetch_bounded_public_surface", return_value=live_content):
                errors, _resolved = MODULE._surface_inspection_errors(
                    self.contract,
                    {surface: inspection},
                    {},
                    ROOT,
                )
            with mock.patch.object(
                MODULE,
                "_fetch_bounded_public_surface",
                return_value=b"<html><body>Changed public proof claim</body></html>",
            ):
                changed_errors, _resolved = MODULE._surface_inspection_errors(
                    self.contract,
                    {surface: inspection},
                    {},
                    ROOT,
                )
            with mock.patch.object(
                MODULE,
                "_fetch_bounded_public_surface",
                side_effect=MODULE.HTTPException("truncated transport"),
            ):
                transport_errors, _resolved = MODULE._surface_inspection_errors(
                    self.contract,
                    {surface: inspection},
                    {},
                    ROOT,
                )
            with mock.patch.object(
                MODULE,
                "_fetch_bounded_public_surface",
                return_value=(
                    b"<html><body>Bounded proof claim"
                    b"<script>window.contact='private@example.invalid'</script></body></html>"
                ),
            ):
                private_raw_errors, _resolved = MODULE._surface_inspection_errors(
                    self.contract,
                    {surface: inspection},
                    {},
                    ROOT,
                )
            with mock.patch.object(
                MODULE,
                "_fetch_bounded_public_surface",
                return_value=b"<html><body data-contact='+44 20 7946 0958'>Bounded proof claim</body></html>",
            ):
                private_phone_errors, _resolved = MODULE._surface_inspection_errors(
                    self.contract,
                    {surface: inspection},
                    {},
                    ROOT,
                )
        self.assertFalse(any("raw response differs" in error for error in errors), errors)
        self.assertFalse(any("visible claims differ" in error for error in errors), errors)
        self.assertTrue(any("visible claims differ" in error for error in changed_errors), changed_errors)
        self.assertTrue(
            any("live surface inspection could not reproduce" in error for error in transport_errors),
            transport_errors,
        )
        self.assertTrue(
            any("raw response contains private material" in error for error in private_raw_errors),
            private_raw_errors,
        )
        self.assertTrue(
            any("raw response contains private material" in error for error in private_phone_errors),
            private_phone_errors,
        )
        legacy_inspection = copy.deepcopy(inspection)
        legacy_inspection["raw_response_sha256"] = "0" * 64
        with mock.patch.object(
            MODULE,
            "EXPECTED_SURFACE_LEVELS",
            {surface: self.contract["surface_audit_model"]["surface_levels"][surface]},
        ):
            legacy_errors, _resolved = MODULE._surface_inspection_errors(
                self.contract,
                {surface: legacy_inspection},
                {},
                ROOT,
            )
        self.assertTrue(any("invalid exact schema" in error for error in legacy_errors), legacy_errors)

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

    def test_w07_authority_read_ignores_ambient_proxy_and_ca_overrides(self) -> None:
        receipt_url = "https://github.com/organvm/limen/issues/2188#issuecomment-1"
        comment = {
            "html_url": receipt_url,
            "user": {"login": "4444J99"},
            "author_association": "MEMBER",
            "body": "synthetic transport fixture",
        }
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "trusted-ca.pem"
            bundle.write_text("test trust bundle", encoding="utf-8")
            context = mock.MagicMock()
            response = mock.MagicMock()
            response.read.return_value = json.dumps(comment).encode()
            response.__enter__.return_value = response
            opener = mock.MagicMock()
            opener.open.return_value = response
            with mock.patch.object(MODULE, "CONTRACT_CA_BUNDLE_CANDIDATES", (bundle,)):
                with mock.patch.object(MODULE.ssl, "SSLContext", return_value=context):
                    with mock.patch.object(MODULE, "build_opener", return_value=opener) as build:
                        with mock.patch.dict(
                            os.environ,
                            {
                                "HTTPS_PROXY": "http://proxy.invalid",
                                "SSL_CERT_FILE": "/tmp/untrusted-cert.pem",
                            },
                            clear=False,
                        ):
                            observed = MODULE._fetch_github_issue_comment(receipt_url, "PSP-P03-W07")
        self.assertEqual(comment, observed)
        context.load_verify_locations.assert_called_once_with(cafile=str(bundle))
        handlers = build.call_args.args
        proxy = next(handler for handler in handlers if isinstance(handler, MODULE.ProxyHandler))
        https = next(handler for handler in handlers if isinstance(handler, MODULE.HTTPSHandler))
        self.assertEqual({}, proxy.proxies)
        self.assertIs(context, https._context)
        opener.open.assert_called_once_with(mock.ANY, timeout=30)

    def test_live_w07_verifier_authenticates_the_receipt_comment_actor(self) -> None:
        receipt_url = "https://github.com/organvm/limen/issues/2188#issuecomment-1"
        completed = subprocess.CompletedProcess(
            [],
            0,
            json.dumps(
                {
                    "status": "pass",
                    "work_id": "PSP-P03-W07",
                    "receipt_url": receipt_url,
                    "receipt_sha256": "a" * 64,
                }
            ),
            "",
        )
        injected = {
            "PATH": "/tmp/untrusted-bin",
            "PYTHONPATH": "/tmp/untrusted-python",
            "PYTHONHOME": "/tmp/untrusted-home",
            "LD_PRELOAD": "/tmp/untrusted.so",
            "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
        }
        with mock.patch.dict(os.environ, injected, clear=False):
            with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
                with mock.patch.object(
                    MODULE,
                    "_fetch_github_issue_comment",
                    return_value={"user": {"login": "outside-user"}, "author_association": "NONE"},
                ):
                    with self.assertRaisesRegex(ValueError, "authorized repository actor"):
                        MODULE._live_w07_verification(ROOT)
        argv = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual(Path(sys.executable).resolve(), Path(argv[0]))
        self.assertEqual(["--verify-work", "PSP-P03-W07"], argv[-2:])
        for key in set(injected) - {"PATH"}:
            self.assertNotIn(key, environment)
        self.assertNotIn(injected["PATH"], environment["PATH"].split(os.pathsep))

    def test_w07_validator_uses_the_trusted_interpreter_without_runtime_hooks(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "PASS\n", "")
        injected = {
            "PYTHONPATH": "/tmp/untrusted-python",
            "PYTHONHOME": "/tmp/untrusted-home",
            "LD_PRELOAD": "/tmp/untrusted.so",
            "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
        }
        with tempfile.TemporaryDirectory() as directory:
            response = Path(directory) / "response.json"
            response.write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, injected, clear=False):
                with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
                    observed = MODULE._run_trusted_w07_validator(response)
        self.assertEqual(completed.returncode, observed.returncode)
        self.assertEqual(completed.stdout, observed.stdout)
        self.assertEqual(completed.stderr, observed.stderr)
        argv = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        dependency_archive = run.call_args.kwargs["input"]
        self.assertEqual(Path(sys.executable).resolve(), Path(argv[0]))
        self.assertEqual(["-I", "-S", "-B", "-c"], argv[1:5])
        self.assertEqual(MODULE.W07_REPLAY_BOOTSTRAP, argv[5])
        self.assertEqual("script", argv[-3])
        self.assertEqual((ROOT / MODULE.W07_VALIDATOR_PATH).resolve(), Path(argv[-2]))
        self.assertIsInstance(dependency_archive, bytes)
        self.assertEqual(hashlib.sha256(dependency_archive).hexdigest(), argv[9])
        self.assertEqual(len(dependency_archive), int(argv[10]))
        self.assertFalse(run.call_args.kwargs["text"])
        for key in injected:
            self.assertNotIn(key, environment)
        self.assertEqual("1", environment["PYTHONNOUSERSITE"])
        self.assertEqual("1", environment["PYTHONSAFEPATH"])

    def test_w07_replay_uses_validator_and_workflow_from_the_observed_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            response_blob = subprocess.run(
                ["git", "show", f"{head}:{response_path}"],
                cwd=repository,
                check=True,
                capture_output=True,
            ).stdout
            canonical_objects: dict[tuple[str, str], tuple[bytes, str]] = {}
            for path in MODULE.W07_REPLAY_PATHS:
                content, blob = MODULE._read_git_object_bytes(repository, head, path)
                assert content is not None and blob is not None
                canonical_objects[(head, path)] = (content, blob)
            (repository / MODULE.W07_VALIDATOR_PATH).write_text(
                "raise SystemExit('untrusted current validator')\n",
                encoding="utf-8",
            )
            (repository / MODULE.W07_WORKFLOW_PATH).write_text(
                "raise SystemExit('untrusted current workflow')\n",
                encoding="utf-8",
            )
            with tempfile.TemporaryDirectory() as poisoned_directory:
                poison = Path(poisoned_directory)
                (poison / "sitecustomize.py").write_text("raise SystemExit('ambient site hook executed')\n")
                injected = {
                    "PYTHONPATH": str(poison),
                    "LD_PRELOAD": "/tmp/untrusted.so",
                    "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
                }
                with mock.patch.dict(os.environ, injected, clear=False):
                    completed, memo = MODULE._run_observed_w07_replay(head, response_blob, canonical_objects)
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        self.assertIn(b"# PSP-P03-W07 blinded-reader decision memo", memo)

    def test_live_phase_verification_executes_and_binds_manifest_phase_proof(self) -> None:
        phase_id = "PSP-P03"
        receipt_url = "https://github.com/organvm/limen/issues/2181#issuecomment-1"
        proof = {
            "status": "pass",
            "phase_id": phase_id,
            "exit_gate_sha256": "a" * 64,
            "child_receipts_sha256": "b" * 64,
            "child_receipt_evidence": {},
            "remote_state_sha256": "c" * 64,
            "parity_sha256": "d" * 64,
        }
        proof_stdout = json.dumps(proof, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        proof_sha256 = hashlib.sha256(proof_stdout.encode()).hexdigest()
        predicate = {
            "command": f"python3 scripts/positioning-program.py --phase-proof {phase_id}",
            "exit_code": 0,
            "output_sha256": proof_sha256,
            "observed_at": "2026-08-14T12:00:00Z",
        }
        receipt = {
            **proof,
            "schema_version": "limen.positioning_phase_receipt.v1",
            "observed_heads": {"organvm/limen": MODULE.C03_CURRENT_HEAD},
            "predicate": predicate,
            "evidence_urls": ["https://github.com/organvm/limen/issues/2181"],
        }
        receipt.pop("child_receipt_evidence")
        receipt_sha256 = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        verification = {
            "status": "pass",
            "phase_id": phase_id,
            "receipt_url": receipt_url,
            "receipt_sha256": receipt_sha256,
        }
        completed = [
            subprocess.CompletedProcess([], 0, proof_stdout, ""),
            subprocess.CompletedProcess([], 0, json.dumps(verification), ""),
        ]
        comment = {
            "html_url": receipt_url,
            "user": {"login": "4444J99"},
            "author_association": "MEMBER",
            "body": (f"<!-- positioning-phase-receipt:{phase_id} -->\n```json\n" + json.dumps(receipt) + "\n```"),
        }
        injected = {
            "PATH": "/tmp/untrusted-bin",
            "PYTHONPATH": "/tmp/untrusted-python",
            "PYTHONHOME": "/tmp/untrusted-home",
            "LD_PRELOAD": "/tmp/untrusted.so",
            "LD_LIBRARY_PATH": "/tmp/untrusted-lib",
            "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
        }
        with mock.patch.dict(os.environ, injected, clear=False):
            with mock.patch.object(MODULE.subprocess, "run", side_effect=completed) as run:
                with mock.patch.object(MODULE, "_fetch_github_issue_comment", return_value=comment):
                    observed = MODULE._live_phase_verification(ROOT, phase_id)
        self.assertEqual(proof, observed["phase_proof"])
        self.assertEqual(proof_sha256, observed["phase_proof_output_sha256"])
        self.assertEqual(predicate, observed["phase_proof_predicate"])
        self.assertEqual("--phase-proof", run.call_args_list[0].args[0][-2])
        self.assertEqual("--verify-phase", run.call_args_list[1].args[0][-2])
        for call in run.call_args_list:
            argv = call.args[0]
            environment = call.kwargs["env"]
            self.assertEqual(Path(sys.executable).resolve(), Path(argv[0]))
            self.assertEqual("-I", argv[1])
            self.assertEqual("-S", argv[2])
            self.assertEqual("-B", argv[3])
            self.assertEqual("-c", argv[4])
            self.assertEqual(MODULE.POSITIONING_PROGRAM_BOOTSTRAP, argv[5])
            self.assertEqual((ROOT / "scripts/positioning-program.py").resolve(), Path(argv[-3]))
            for key in set(injected) - {"PATH"}:
                self.assertNotIn(key, environment)
            self.assertNotIn(injected["PATH"], environment["PATH"].split(os.pathsep))
            self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
            self.assertEqual("1", environment["PYTHONNOUSERSITE"])
            self.assertEqual("1", environment["PYTHONSAFEPATH"])

        for mutation, expected_error in (
            ({"customer_email": "reader@example.invalid"}, "invalid exact schema"),
            (
                {"evidence_urls": ["https://example.com/proof?access_token=plainvalue"]},
                "private or credential material",
            ),
        ):
            changed_receipt = copy.deepcopy(receipt)
            changed_receipt.update(mutation)
            changed_digest = hashlib.sha256(
                json.dumps(changed_receipt, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            changed_verification = {**verification, "receipt_sha256": changed_digest}
            changed_comment = {
                **comment,
                "body": (
                    f"<!-- positioning-phase-receipt:{phase_id} -->\n```json\n" + json.dumps(changed_receipt) + "\n```"
                ),
            }
            with self.subTest(expected_error=expected_error):
                changed_completed = [
                    subprocess.CompletedProcess([], 0, proof_stdout, ""),
                    subprocess.CompletedProcess([], 0, json.dumps(changed_verification), ""),
                ]
                with mock.patch.object(MODULE.subprocess, "run", side_effect=changed_completed):
                    with mock.patch.object(MODULE, "_fetch_github_issue_comment", return_value=changed_comment):
                        with self.assertRaisesRegex(ValueError, expected_error):
                            MODULE._live_phase_verification(ROOT, phase_id)

    @staticmethod
    def _installed_pyyaml_sources() -> list[tuple[MODULE.PurePosixPath, bytes]]:
        package_root = next(
            candidate for raw_path in sys.path if raw_path if (candidate := Path(raw_path).resolve() / "yaml").is_dir()
        )
        tree_sha256, sources = MODULE._python_source_tree(package_root)
        if tree_sha256 != MODULE.TRUSTED_PYYAML_DEPENDENCY["python_source_tree_sha256"]:
            raise AssertionError("test interpreter does not expose the contract-owned PyYAML tree")
        return sources

    @staticmethod
    def _write_pyyaml_sources(
        root: Path,
        sources: list[tuple[MODULE.PurePosixPath, bytes]],
    ) -> None:
        for relative, data in sources:
            destination = root / "yaml" / Path(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

    def test_phase_proof_rejects_a_sibling_pyyaml_source_mutation(self) -> None:
        sources = self._installed_pyyaml_sources()
        with tempfile.TemporaryDirectory() as directory:
            dependency_root = Path(directory) / "site-packages"
            dependency_root.mkdir()
            self._write_pyyaml_sources(dependency_root, sources)
            constructor = dependency_root / "yaml/constructor.py"
            constructor.write_bytes(constructor.read_bytes() + b"\n# drift\n")
            with mock.patch.object(MODULE.sys, "path", [str(dependency_root)]):
                with self.assertRaisesRegex(OSError, "complete contract-owned PyYAML source tree"):
                    MODULE._run_trusted_positioning_program(
                        ROOT,
                        "--phase-proof",
                        "PSP-P03",
                        timeout=90,
                    )

    def test_phase_proof_copies_only_the_authenticated_pyyaml_sources(self) -> None:
        sources = self._installed_pyyaml_sources()
        with tempfile.TemporaryDirectory() as directory:
            dependency_root = Path(directory) / "site-packages"
            dependency_root.mkdir()
            self._write_pyyaml_sources(dependency_root, sources)
            (dependency_root / "sitecustomize.py").write_text("raise RuntimeError('must not be copied')\n")

            def inspect_copy(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                copied_root = Path(argv[6])
                self.assertEqual({"yaml"}, {path.name for path in copied_root.iterdir()})
                self.assertFalse((copied_root / "sitecustomize.py").exists())
                copied_sha256, copied_sources = MODULE._python_source_tree(copied_root / "yaml")
                self.assertEqual(MODULE.TRUSTED_PYYAML_DEPENDENCY["python_source_tree_sha256"], copied_sha256)
                self.assertEqual(MODULE.TRUSTED_PYYAML_DEPENDENCY["python_source_file_count"], len(copied_sources))
                return subprocess.CompletedProcess(argv, 0, "", "")

            with mock.patch.object(MODULE.sys, "path", [str(dependency_root)]):
                with mock.patch.object(MODULE.subprocess, "run", side_effect=inspect_copy):
                    completed = MODULE._run_trusted_positioning_program(
                        ROOT,
                        "--phase-proof",
                        "PSP-P03",
                        timeout=90,
                    )
            self.assertEqual(0, completed.returncode)

    def test_w07_dependency_rejects_a_sibling_source_mutation(self) -> None:
        sources = MODULE._trusted_w07_jsonschema_sources()
        with tempfile.TemporaryDirectory() as directory:
            site_root = Path(directory) / "site-packages"
            site_root.mkdir()
            for relative, data in sources:
                destination = site_root.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            validator = site_root / "jsonschema/validators.py"
            validator.write_bytes(validator.read_bytes() + b"\n# untrusted sibling mutation\n")
            with mock.patch.object(MODULE.sys, "path", [str(site_root)]):
                with self.assertRaisesRegex(OSError, "complete contract-owned W07 jsonschema dependency tree"):
                    MODULE._trusted_w07_jsonschema_sources()

    def test_w07_dependency_archive_contains_only_authenticated_sources_in_memory(self) -> None:
        sources = MODULE._trusted_w07_jsonschema_sources()
        dependency_archive = MODULE._w07_jsonschema_dependency_archive(sources)
        self.assertEqual(dependency_archive, MODULE._w07_jsonschema_dependency_archive(sources))
        with MODULE.zipfile.ZipFile(io.BytesIO(dependency_archive)) as archive:
            infos = archive.infolist()
            expected = {
                *MODULE.TRUSTED_W07_JSONSCHEMA_DEPENDENCY["package_roots"],
                "rpds",
                *MODULE.TRUSTED_W07_JSONSCHEMA_DEPENDENCY["single_files"],
            }
            self.assertEqual(expected, {Path(info.filename).parts[0] for info in infos})
            self.assertNotIn("sitecustomize.py", {info.filename for info in infos})
            self.assertTrue(all(info.compress_type == MODULE.zipfile.ZIP_STORED for info in infos))
            self.assertEqual(
                MODULE.TRUSTED_W07_JSONSCHEMA_DEPENDENCY["rpds_compat_sha256"],
                hashlib.sha256(archive.read("rpds/__init__.py")).hexdigest(),
            )

        completed = subprocess.CompletedProcess([], 0, b"PASS\n", b"")
        with tempfile.TemporaryDirectory() as directory:
            response = Path(directory) / "response.json"
            response.write_text("{}", encoding="utf-8")
            with mock.patch.object(Path, "write_bytes", side_effect=AssertionError("dependency write")):
                with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
                    MODULE._run_trusted_w07_validator(response)
        self.assertEqual(dependency_archive, run.call_args.kwargs["input"])

    def test_w07_dependency_bootstrap_rejects_changed_and_traversal_entries(self) -> None:
        sources = MODULE._trusted_w07_jsonschema_sources()
        archive = MODULE._w07_jsonschema_dependency_archive(sources)
        validator = (ROOT / MODULE.W07_VALIDATOR_PATH).resolve()
        with tempfile.TemporaryDirectory() as directory:
            response = Path(directory) / "response.json"
            response.write_text("{}", encoding="utf-8")
            mutations: list[tuple[bytes, str]] = []
            for changed_name, changed_data in (
                ("jsonschema/validators.py", b"raise SystemExit('changed')\n"),
                ("../sitecustomize.py", b"raise SystemExit('ambient hook')\n"),
            ):
                output = io.BytesIO()
                with MODULE.zipfile.ZipFile(io.BytesIO(archive)) as source_archive:
                    with MODULE.zipfile.ZipFile(
                        output,
                        "w",
                        compression=MODULE.zipfile.ZIP_STORED,
                    ) as changed_archive:
                        for info in source_archive.infolist():
                            if info.filename != changed_name:
                                changed_archive.writestr(info, source_archive.read(info))
                        changed_archive.writestr(changed_name, changed_data)
                mutations.append((output.getvalue(), changed_name))

            for changed_archive, changed_name in mutations:
                completed = subprocess.run(
                    [
                        str(Path(sys.executable).resolve()),
                        "-I",
                        "-S",
                        "-B",
                        "-c",
                        MODULE.W07_REPLAY_BOOTSTRAP,
                        *MODULE._w07_replay_arguments(changed_archive, "script", validator, response),
                    ],
                    cwd=ROOT,
                    env=MODULE._w07_replay_environment(Path(sys.executable).resolve()),
                    check=False,
                    capture_output=True,
                    input=changed_archive,
                    timeout=90,
                )
                self.assertNotEqual(0, completed.returncode, changed_name)

    def test_live_phase_verification_cannot_accept_receipt_without_current_phase_proof(self) -> None:
        failed = subprocess.CompletedProcess([], 2, "", "phase proof failed")
        with mock.patch.object(MODULE.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(ValueError, "manifest phase proof did not pass"):
                MODULE._live_phase_verification(ROOT, "PSP-P03")
        self.assertEqual(1, run.call_count)

    def test_receipt_privacy_scan_rejects_assignments_and_credential_url_parameters(self) -> None:
        for assignment in (
            "The password is hunter2alpha",
            "token is hunter2alpha",
            "token:\nhunter2alpha",  # allow-secret: synthetic adversarial fixture
            "token:\u2028hunter2alpha",  # allow-secret: synthetic adversarial fixture
            "token:\u2029hunter2alpha",  # allow-secret: synthetic adversarial fixture
            "credential: hunter2alpha",
        ):
            with self.subTest(assignment=assignment):
                self.assertEqual(
                    {"$.limitations[0]"},
                    MODULE._find_forbidden_demo_material({"limitations": [assignment]}),
                )
        self.assertEqual(
            {"$.evidence_urls[0]"},
            MODULE._find_forbidden_demo_material(
                {"evidence_urls": ["https://example.com/proof?access_token=plainvalue"]}
            ),
        )
        for credential_key in (
            "api%5Fkey",
            "private%5Fkey",
            "recovery%5Fcode",
            "authorization",
            "session%5Fcookie",
        ):
            self.assertEqual(
                {"$.evidence_urls[0]"},
                MODULE._find_forbidden_demo_material(
                    {"evidence_urls": [f"https://example.com/proof?{credential_key}=plainvalue"]}
                ),
                credential_key,
            )
        self.assertEqual(
            set(),
            MODULE._find_forbidden_demo_material({"evidence_urls": ["https://example.com/proof?claim_id=CLM-1"]}),
        )
        self.assertEqual(
            set(),
            MODULE._find_forbidden_demo_material({"limitations": ["API_" + "KEY" + "=\n# intentionally blank"]}),
        )
        for safe_statement in ("token is required", "token budget is bounded"):
            with self.subTest(safe_statement=safe_statement):
                self.assertEqual(
                    set(),
                    MODULE._find_forbidden_demo_material({"limitations": [safe_statement]}),
                )
        self.assertEqual(
            {"$.limitations[0]"},
            MODULE._find_forbidden_demo_material(
                {"limitations": ["See https://example.com/proof?api%5Fkey=plainvalue for proof."]}
            ),
        )

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

    def test_surface_audit_requires_exact_private_safe_row_schema(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        manifest_rows[0]["password"] = "hunter2alpha"
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("unexpected exact-schema fields: password" in error for error in result["errors"]))
        self.assertTrue(any("surface row contains private material" in error for error in result["errors"]))

    def test_surface_audit_privacy_scans_inspection_identifiers_with_telephone_rules(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        manifest = self._empty_surface_manifest(rows)
        inspections = manifest["surface_inspections"]
        assert isinstance(inspections, dict)
        surface = next(iter(inspections))
        private_inspection_id = "phone: 2125551234"
        inspections[surface]["inspection_id"] = private_inspection_id
        manifest_rows = manifest["rows"]
        assert isinstance(manifest_rows, list)
        for row in manifest_rows:
            if row["surface"] == surface:
                row["inspection_id"] = private_inspection_id
        result = MODULE.audit_surface_manifest(self.contract, manifest)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("surface inspection contains private material" in error for error in result["errors"]))
        self.assertTrue(any("surface row contains private material" in error for error in result["errors"]))

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

    def test_absent_surface_claim_requires_complete_canonical_evidence(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        for field in (
            "source_ids",
            "observed_at",
            "status",
            "disclosure_level",
            "canonical_or_drift",
            "action",
        ):
            with self.subTest(field=field):
                manifest = self._empty_surface_manifest(rows)
                manifest_rows = manifest["rows"]
                assert isinstance(manifest_rows, list)
                manifest_rows[0].pop(field)
                result = MODULE.audit_surface_manifest(self.contract, manifest)
                self.assertEqual("fail", result["status"])
                self.assertTrue(
                    any(
                        "absent claim missing required evidence fields" in error or "differs from canonical" in error
                        for error in result["errors"]
                    ),
                    result["errors"],
                )

        for field, value in (
            ("source_ids", ["unreviewed-source"]),
            ("observed_at", ["2099-01-01"]),
            ("status", "verified" if rows[0]["status"] != "verified" else "withheld"),
            ("disclosure_level", "L9"),
            ("canonical_or_drift", "canonical"),
            ("action", "audit_canonical_wording"),
        ):
            with self.subTest(field=field, value=value):
                manifest = self._empty_surface_manifest(rows)
                manifest_rows = manifest["rows"]
                assert isinstance(manifest_rows, list)
                manifest_rows[0][field] = value
                result = MODULE.audit_surface_manifest(self.contract, manifest)
                self.assertEqual("fail", result["status"])
                self.assertTrue(any("differ" in error for error in result["errors"]), result["errors"])

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

    def test_demo_requires_contract_owned_synthetic_ids_and_bounded_values(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        for record_type, field, value in (
            ("packet", "id", "real-packet-id"),
            ("failure", "reason", "private repository detail"),
            ("recovery", "action", "contact a customer"),
            ("harvest", "outcome", "real run retained"),
        ):
            with self.subTest(record_type=record_type, field=field):
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                record = next(row for row in fixture["records"] if row["type"] == record_type)
                record[field] = value
                result = MODULE.validate_demo_fixture(self.contract, fixture)
                self.assertEqual("fail", result["status"])
                self.assertTrue(
                    any(
                        "synthetic namespace" in error or "bounded synthetic vocabulary" in error
                        for error in result["errors"]
                    ),
                    result["errors"],
                )

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

        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        lease = next(row for row in fixture["records"] if row["type"] == "lease")
        lease["packet_id"] = {"unexpected": "object"}
        result = MODULE.validate_demo_fixture(self.contract, fixture)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("field packet_id must be nonblank text" in error for error in result["errors"]))

    def test_demo_failure_branch_requires_a_failed_or_blocked_predicate(self) -> None:
        fixture_path = ROOT / "scripts/tests/fixtures/positioning-proof/synthetic-architecture-demo.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        predicate = next(row for row in fixture["records"] if row["type"] == "predicate")
        predicate["result"] = "pass"
        result = MODULE.validate_demo_fixture(self.contract, fixture)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("failed or blocked predicate" in error for error in result["errors"]))

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
        self.assertEqual(0, result["substantive_public_count"])
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
        self.assertEqual(0, result["substantive_public_count"])
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
        self.assertEqual(0, result["substantive_public_count"])
        self.assertTrue(any("public consent disposition" in error for error in result["errors"]))

    def test_external_validation_rejects_unhashable_object_class_without_crashing(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        for index in range(2):
            row = {field: f"value-{index}-{field}" for field in required}
            row["object class"] = self.contract["external_validation"]["acceptable_objects"][index]
            row["independence disclosure"] = "independent_third_party"
            row["object URL or receipt"] = f"https://example.invalid/class-{index}"
            row["date"] = "2026-08-14"
            row["consent status"] = "public_consented"
            objects.append(row)
        objects[0]["object class"] = ["independent reproduction"]
        result = MODULE.validate_external_objects(
            self.contract,
            {"outreach_performed": False, "objects": objects},
        )
        self.assertEqual("fail", result["status"])
        self.assertEqual(0, result["substantive_public_count"])
        self.assertTrue(any("approved object class" in error for error in result["errors"]))

    def test_external_validation_authenticates_and_binds_each_independent_review(self) -> None:
        required = self.contract["external_validation"]["minimum_fields"]
        objects = []
        comments = {}
        for index in range(2):
            receipt_url = f"https://github.com/organvm/limen/issues/2201#issuecomment-{index + 1}"
            row = {field: f"value-{index}-{field}" for field in required}
            row.update(
                {
                    "object class": self.contract["external_validation"]["acceptable_objects"][index],
                    "independence disclosure": "independent_third_party",
                    "object URL or receipt": receipt_url,
                    "date": "2026-08-14",
                    "consent status": "public_consented",
                }
            )
            actor = f"independent-reviewer-{index}"
            receipt = {
                "schema_version": MODULE.EXTERNAL_VALIDATION_RECEIPT_SCHEMA,
                "evidence_kind": "external_validation",
                "subject_sha256": MODULE._canonical_external_validation_subject(row),
                "actor_identity": actor,
                "observed_at": "2026-08-14T12:00:00Z",
                "limitations": ["Hermetic independent-review fixture only."],
            }
            row["receipt SHA-256"] = hashlib.sha256(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            comments[receipt_url] = {
                "html_url": receipt_url,
                "user": {"login": actor},
                "author_association": "NONE",
                "created_at": "2026-08-14T11:59:00Z",
                "updated_at": receipt["observed_at"],
                "body": "<!-- positioning-external-validation-receipt -->\n```json\n" + json.dumps(receipt) + "\n```",
            }
            objects.append(row)
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            result = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("pass", result["status"])
        self.assertEqual(2, result["substantive_public_count"])

        first_url = objects[0]["object URL or receipt"]
        safe_body = comments[first_url]["body"]
        private_receipt = json.loads(MODULE.EXTERNAL_VALIDATION_RECEIPT_BLOCK.findall(safe_body)[0])
        private_receipt["limitations"] = ["The password is hunter2alpha."]
        comments[first_url]["body"] = (
            "<!-- positioning-external-validation-receipt -->\n```json\n" + json.dumps(private_receipt) + "\n```"
        )
        objects[0]["receipt SHA-256"] = hashlib.sha256(
            json.dumps(private_receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            private_authority = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", private_authority["status"])
        self.assertEqual(1, private_authority["substantive_public_count"])
        self.assertTrue(any("private or credential material" in error for error in private_authority["errors"]))
        comments[first_url]["body"] = safe_body
        safe_receipt = json.loads(MODULE.EXTERNAL_VALIDATION_RECEIPT_BLOCK.findall(safe_body)[0])
        objects[0]["receipt SHA-256"] = hashlib.sha256(
            json.dumps(safe_receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        first_comment = comments[objects[0]["object URL or receipt"]]
        first_comment["updated_at"] = "2026-08-14T11:59:30Z"
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            timestamp_mismatch = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", timestamp_mismatch["status"])
        self.assertEqual(1, timestamp_mismatch["substantive_public_count"])
        self.assertTrue(any("authenticated comment version" in error for error in timestamp_mismatch["errors"]))
        first_comment["updated_at"] = "2026-08-14T12:00:00Z"

        authenticated_comment = copy.deepcopy(first_comment)
        timestamp_cases = (
            ({key: value for key, value in authenticated_comment.items() if key != "created_at"}, "timestamps"),
            ({**authenticated_comment, "created_at": "2026-08-14T12:01:00Z"}, "chronologically"),
            ({**authenticated_comment, "updated_at": "2999-08-14T12:00:00Z"}, "chronologically"),
        )
        for malformed_comment, expected_error in timestamp_cases:
            with self.subTest(expected_error=expected_error):
                comments[objects[0]["object URL or receipt"]] = malformed_comment
                with mock.patch.object(
                    MODULE,
                    "_fetch_github_issue_comment",
                    side_effect=lambda receipt_url, _label: comments[receipt_url],
                ):
                    malformed_time = MODULE.validate_external_objects(
                        self.contract,
                        {"outreach_performed": False, "objects": objects},
                        as_of=date(2026, 8, 14),
                    )
                self.assertEqual("fail", malformed_time["status"])
                self.assertTrue(any(expected_error in error for error in malformed_time["errors"]))
        comments[objects[0]["object URL or receipt"]] = first_comment

        objects[0]["receipt SHA-256"] = "0" * 64
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            digest_mismatch = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", digest_mismatch["status"])
        self.assertEqual(1, digest_mismatch["substantive_public_count"])
        self.assertTrue(any("digest differs" in error for error in digest_mismatch["errors"]))
        objects[0]["receipt SHA-256"] = hashlib.sha256(
            json.dumps(
                json.loads(
                    MODULE.EXTERNAL_VALIDATION_RECEIPT_BLOCK.findall(
                        comments[objects[0]["object URL or receipt"]]["body"]
                    )[0]
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        original_comment_body = comments[objects[0]["object URL or receipt"]]["body"]
        edited_receipt = json.loads(MODULE.EXTERNAL_VALIDATION_RECEIPT_BLOCK.findall(original_comment_body)[0])
        edited_receipt["limitations"] = ["Edited after the bound digest was recorded."]
        comments[objects[0]["object URL or receipt"]]["body"] = (
            "<!-- positioning-external-validation-receipt -->\n```json\n" + json.dumps(edited_receipt) + "\n```"
        )
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            edited_comment = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", edited_comment["status"])
        self.assertEqual(1, edited_comment["substantive_public_count"])
        comments[objects[0]["object URL or receipt"]]["body"] = original_comment_body

        original_method = objects[0]["method"]
        objects[0]["method"] = "reviewer@example.invalid"
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            private_value = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", private_value["status"])
        self.assertEqual(1, private_value["substantive_public_count"])
        self.assertTrue(any("contains private material" in error for error in private_value["errors"]))
        objects[0]["method"] = original_method

        objects[0]["review metadata"] = {"credential": "synthetic-secret"}
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            private_extra = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", private_extra["status"])
        self.assertEqual(1, private_extra["substantive_public_count"])
        self.assertTrue(any("unexpected fields" in error for error in private_extra["errors"]))
        self.assertTrue(any("contains private material" in error for error in private_extra["errors"]))
        objects[0].pop("review metadata")

        first_url = objects[0]["object URL or receipt"]
        assert isinstance(first_url, str)
        original_body = comments[first_url]["body"]
        marked = MODULE.EXTERNAL_VALIDATION_RECEIPT_BLOCK.findall(original_body)
        duplicate_receipt = marked[0][:-1] + ',"actor_identity":"independent-reviewer-0"}'
        comments[first_url]["body"] = (
            "<!-- positioning-external-validation-receipt -->\n```json\n" + duplicate_receipt + "\n```"
        )
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            duplicate = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", duplicate["status"])
        self.assertEqual(1, duplicate["substantive_public_count"])
        self.assertTrue(any("duplicate JSON member: actor_identity" in error for error in duplicate["errors"]))
        comments[first_url]["body"] = original_body

        objects[0]["method"] = "drifted method"
        with mock.patch.object(
            MODULE,
            "_fetch_github_issue_comment",
            side_effect=lambda receipt_url, _label: comments[receipt_url],
        ):
            drifted = MODULE.validate_external_objects(
                self.contract,
                {"outreach_performed": False, "objects": objects},
                as_of=date(2026, 8, 14),
            )
        self.assertEqual("fail", drifted["status"])
        self.assertEqual(1, drifted["substantive_public_count"])
        self.assertTrue(any("exact asserted review" in error for error in drifted["errors"]))

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
        with (
            mock.patch.object(
                MODULE,
                "_live_authoritative_closure_verification",
                return_value=authoritative,
            ),
            mock.patch.object(MODULE, "_canonical_limen_contains_head", return_value=True),
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
        with (
            mock.patch.object(MODULE, "_live_authoritative_closure_verification", return_value=remote),
            mock.patch.object(MODULE, "_canonical_limen_contains_head", return_value=True),
        ):
            result = MODULE.formalization_readiness(self.contract, closure)
        self.assertFalse(result["ready"])
        self.assertFalse(
            any("final C03 head is not an isolated-canonical descendant" in error for error in result["errors"])
        )

    def test_formalization_proves_the_accepted_floor_in_the_isolated_canonical_store(self) -> None:
        closure = {
            "chunk_id": "PSP-C03",
            "status": "pass",
            "exact_head": MODULE.C03_CURRENT_HEAD,
            "phase_receipts": {},
            "w07_receipt": {},
        }
        remote = {
            "status": "pass",
            "repository": "organvm/limen",
            "closure_head": MODULE.C03_CURRENT_HEAD,
            "default_branch": "main",
            "default_head": MODULE.C03_CURRENT_HEAD,
            "contained": True,
        }
        with (
            mock.patch.object(MODULE, "_live_authoritative_closure_verification", return_value=remote),
            mock.patch.object(MODULE, "_canonical_limen_contains_head", return_value=True) as ancestry,
            mock.patch.object(
                MODULE,
                "_sanitized_ancestry",
                side_effect=AssertionError("caller object store must not decide formalization ancestry"),
            ),
        ):
            result = MODULE.formalization_readiness(self.contract, closure)
        self.assertFalse(result["ready"])
        ancestry.assert_called_once_with(
            "main",
            MODULE.C03_CURRENT_HEAD,
            MODULE.C03_MERGE_COMMIT,
            MODULE.C03_CURRENT_HEAD,
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

    def test_live_closure_ancestry_uses_the_isolated_canonical_store(self) -> None:
        with (
            mock.patch.object(
                MODULE,
                "_canonical_limen_remote_head",
                return_value=("main", MODULE.C03_MERGE_COMMIT),
            ),
            mock.patch.object(
                MODULE,
                "_canonical_limen_containment",
                return_value={MODULE.C03_MERGE_COMMIT: True},
            ) as contains,
        ):
            result = MODULE._live_authoritative_closure_verification(ROOT, MODULE.C03_MERGE_COMMIT)
        self.assertTrue(result["contained"])
        contains.assert_called_once_with(
            "main",
            MODULE.C03_MERGE_COMMIT,
            {MODULE.C03_MERGE_COMMIT},
            None,
        )

    def test_canonical_closure_ancestry_fetches_before_using_the_isolated_object_store(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        fetched = subprocess.CompletedProcess([], 0, MODULE.C03_MERGE_COMMIT + "\n", "")
        with mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=(completed, completed, fetched, completed, completed),
        ) as run:
            self.assertTrue(
                MODULE._canonical_limen_contains_head(
                    "main",
                    MODULE.C03_MERGE_COMMIT,
                    MODULE.C03_MERGE_COMMIT,
                )
            )
        fetch = run.call_args_list[1]
        self.assertIn("--filter=blob:none", fetch.args[0])
        self.assertIn(f"{MODULE.C03_MERGE_COMMIT}:refs/canonical/main", fetch.args[0])
        ancestry = run.call_args_list[-1]
        self.assertIn("--git-dir", ancestry.args[0])
        self.assertEqual("1", ancestry.kwargs["env"]["GIT_NO_REPLACE_OBJECTS"])
        self.assertEqual(MODULE.os.devnull, ancestry.kwargs["env"]["GIT_GRAFT_FILE"])

    def test_canonical_formalization_ancestry_fetches_both_exact_heads_before_proving_containment(self) -> None:
        accepted_head = "a" * 40
        closure_head = "b" * 40
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        fetched = subprocess.CompletedProcess([], 0, MODULE.C03_CURRENT_HEAD + "\n", "")
        with mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=(completed, completed, fetched, completed, completed, completed),
        ) as run:
            self.assertTrue(
                MODULE._canonical_limen_contains_head(
                    "main",
                    MODULE.C03_CURRENT_HEAD,
                    accepted_head,
                    closure_head,
                )
            )
        fetch = run.call_args_list[1]
        self.assertIn(f"{MODULE.C03_CURRENT_HEAD}:refs/canonical/main", fetch.args[0])
        accepted_lookup = run.call_args_list[3]
        closure_lookup = run.call_args_list[4]
        self.assertIn(f"{accepted_head}^{{commit}}", accepted_lookup.args[0])
        self.assertIn(f"{closure_head}^{{commit}}", closure_lookup.args[0])
        ancestry = run.call_args_list[5]
        self.assertEqual(accepted_head, ancestry.args[0][-2])
        self.assertEqual(closure_head, ancestry.args[0][-1])
        self.assertIn("--git-dir", ancestry.args[0])

    def test_surface_authority_fetches_exact_main_before_reading_receipt_blobs(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        fetched = subprocess.CompletedProcess([], 0, MODULE.C03_MERGE_COMMIT + "\n", "")
        content = subprocess.CompletedProcess([], 0, b"bounded receipt\n", b"")
        blob = subprocess.CompletedProcess([], 0, "b" * 40 + "\n", "")
        with mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=(
                completed,
                completed,
                completed,
                completed,
                completed,
                fetched,
                content,
                blob,
            ),
        ) as run:
            objects = self.fetch_canonical_limen_objects(
                "main",
                MODULE.C03_MERGE_COMMIT,
                {"docs/receipts/positioning/surface-inspections/public-proof.txt"},
            )
        self.assertEqual(
            (b"bounded receipt\n", "b" * 40),
            objects["docs/receipts/positioning/surface-inspections/public-proof.txt"],
        )
        fetch = run.call_args_list[4]
        self.assertIn("--depth=1", fetch.args[0])
        self.assertIn("--filter=blob:none", fetch.args[0])
        self.assertIn("canonical", fetch.args[0])
        self.assertIn(f"{MODULE.C03_MERGE_COMMIT}:refs/canonical/main", fetch.args[0])
        for object_read in run.call_args_list[6:]:
            self.assertIn("--git-dir", object_read.args[0])
            self.assertEqual("1", object_read.kwargs["env"]["GIT_NO_REPLACE_OBJECTS"])
            self.assertEqual(MODULE.os.devnull, object_read.kwargs["env"]["GIT_GRAFT_FILE"])

    def test_evidence_git_object_reads_use_the_sanitized_bounded_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_git = Path(directory) / "git"
            fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            injected = {
                "PATH": directory,
                "GIT_DIR": "/tmp/untrusted.git",
                "GIT_EXEC_PATH": directory,
                "GIT_OBJECT_DIRECTORY": "/tmp/objects",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alternate",
                "GIT_CONFIG_PARAMETERS": "'replace.ref=refs/heads/untrusted'",
                "LD_PRELOAD": "/tmp/untrusted.so",
                "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
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
            self.assertTrue(Path(call.args[0][0]).is_absolute())
            self.assertNotEqual(fake_git, Path(call.args[0][0]))
            self.assertEqual(30, call.kwargs["timeout"])
            environment = call.kwargs["env"]
            self.assertEqual("1", environment["GIT_NO_REPLACE_OBJECTS"])
            for key in injected:
                if key != "PATH":
                    self.assertNotIn(key, environment)
            self.assertNotIn(directory, environment["PATH"].split(os.pathsep))

    def test_dependency_bindings_fetch_canonical_history_before_historical_object_reads(self) -> None:
        authoritative_head = MODULE._canonical_limen_remote_head()[1]
        historical_head = "a" * 40
        path = "docs/positioning/claims-ledger.md"
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        fetched = subprocess.CompletedProcess([], 0, authoritative_head + "\n", "")
        listing = subprocess.CompletedProcess(
            [],
            0,
            f"100644 blob {'b' * 40}\t{path}\0".encode(),
            b"",
        )
        content = b"bounded ledger\n"
        batch = subprocess.CompletedProcess(
            [],
            0,
            f"{'b' * 40} blob {len(content)}\n".encode() + content + b"\n",
            b"",
        )
        with mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=(completed, completed, completed, completed, completed, fetched, completed, listing, batch),
        ) as run:
            observed = self.fetch_canonical_limen_bindings({(historical_head, path)})
        self.assertEqual((b"bounded ledger\n", "b" * 40), observed[(historical_head, path)])
        fetch = run.call_args_list[4].args[0]
        self.assertIn("--filter=blob:none", fetch)
        self.assertNotIn("--depth=1", fetch)
        self.assertIn(f"{authoritative_head}:refs/canonical/main", fetch)
        ancestry = run.call_args_list[6].args[0]
        self.assertIn("--git-dir", ancestry)
        self.assertIn(historical_head, ancestry)
        self.assertIn("ls-tree", run.call_args_list[7].args[0])
        self.assertIn("cat-file", run.call_args_list[8].args[0])
        self.assertEqual((("b" * 40) + "\n").encode(), run.call_args_list[8].kwargs["input"])
        for object_read in run.call_args_list[7:]:
            self.assertIn("--git-dir", object_read.args[0])

    def test_dependency_binding_snapshot_can_anchor_blobs_to_a_closure_descendant(self) -> None:
        authoritative_head = MODULE._canonical_limen_remote_head()[1]
        observed_head = "a" * 40
        closure_head = "c" * 40
        path = "docs/receipts/positioning/psp-p03-w07-reader-responses.json"
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        fetched = subprocess.CompletedProcess([], 0, authoritative_head + "\n", "")
        listing = subprocess.CompletedProcess(
            [],
            0,
            f"100644 blob {'b' * 40}\t{path}\0".encode(),
            b"",
        )
        content = b'{"status":"complete"}\n'
        batch = subprocess.CompletedProcess(
            [],
            0,
            f"{'b' * 40} blob {len(content)}\n".encode() + content + b"\n",
            b"",
        )
        with mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=(
                completed,
                completed,
                completed,
                completed,
                completed,
                fetched,
                completed,
                completed,
                listing,
                batch,
            ),
        ) as run:
            observed = self.fetch_canonical_limen_bindings(
                {(observed_head, path)},
                descendant_head=closure_head,
            )
        self.assertEqual((content, "b" * 40), observed[(observed_head, path)])
        descendant_check = run.call_args_list[6].args[0]
        self.assertIn(f"{closure_head}^{{commit}}", descendant_check)
        ancestry = run.call_args_list[7].args[0]
        self.assertEqual(observed_head, ancestry[-2])
        self.assertEqual(closure_head, ancestry[-1])
        for object_read in run.call_args_list[6:]:
            self.assertIn("--git-dir", object_read.args[0])

    def test_formalization_git_resolver_rejects_mutable_interpreter_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mutable_git = Path(directory) / "git"
            mutable_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            mutable_git.chmod(0o755)
            with (
                mock.patch.object(MODULE.sys, "executable", str(Path(directory) / "python3")),
                mock.patch.object(
                    MODULE,
                    "TRUSTED_EXECUTABLE_DIRECTORIES",
                    (Path(directory), Path("/usr/bin"), Path("/bin")),
                ),
            ):
                resolved = MODULE._trusted_named_executable("git")
        self.assertEqual(Path("/usr/bin/git").resolve(), resolved)
        self.assertNotEqual(mutable_git, resolved)

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
            with (
                mock.patch.object(MODULE, "_canonical_limen_remote_head", return_value=("main", published_head)),
                mock.patch.object(MODULE, "_canonical_limen_contains_head", return_value=False),
            ):
                with self.assertRaisesRegex(ValueError, "authoritative default branch"):
                    MODULE._live_authoritative_closure_verification(repository, unpublished_head)

    def test_phase_receipts_bind_exact_live_marked_receipts(self) -> None:
        bindings, live = self._valid_phase_bindings()
        with (
            mock.patch.object(
                MODULE,
                "_canonical_limen_remote_head",
                return_value=("main", MODULE.C03_CURRENT_HEAD),
            ),
            mock.patch.object(
                MODULE,
                "_canonical_limen_containment",
                return_value={MODULE.C03_CURRENT_HEAD: True},
            ) as contains,
            mock.patch.object(
                MODULE,
                "_sanitized_ancestry",
                side_effect=AssertionError("caller object store must not decide phase ancestry"),
            ),
        ):
            self.assertEqual(
                [],
                MODULE._validate_phase_receipt_bindings(bindings, ROOT, MODULE.C03_CURRENT_HEAD, live),
            )
        contains.assert_called_once_with(
            "main",
            MODULE.C03_CURRENT_HEAD,
            {MODULE.C03_CURRENT_HEAD},
            MODULE.C03_CURRENT_HEAD,
        )
        phase = bindings["PSP-P04"]
        assert isinstance(phase, dict)
        phase["receipt_sha256"] = "c" * 64
        with (
            mock.patch.object(
                MODULE,
                "_canonical_limen_remote_head",
                return_value=("main", MODULE.C03_CURRENT_HEAD),
            ),
            mock.patch.object(
                MODULE,
                "_canonical_limen_containment",
                return_value={MODULE.C03_CURRENT_HEAD: True},
            ),
        ):
            errors = MODULE._validate_phase_receipt_bindings(bindings, ROOT, MODULE.C03_CURRENT_HEAD, live)
        self.assertTrue(any("differs from the latest marked live phase receipt" in error for error in errors))

    def test_phase_receipt_observed_heads_must_precede_the_closure_head(self) -> None:
        bindings, live = self._valid_phase_bindings()
        with (
            mock.patch.object(MODULE, "_canonical_limen_remote_head", return_value=("main", "f" * 40)),
            mock.patch.object(
                MODULE,
                "_canonical_limen_containment",
                return_value={MODULE.C03_CURRENT_HEAD: False},
            ),
        ):
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

    def test_w07_receipt_rejects_extra_and_private_fields_at_every_contract_layer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)

            extra_binding = copy.deepcopy(binding)
            extra_binding["unrecognized"] = "neutral"
            errors = MODULE._validate_w07_receipt_binding(extra_binding, repository, live)
            self.assertTrue(any("exact contract fields" in error for error in errors), errors)

            private_receipt = copy.deepcopy(binding)
            private_receipt["receipt"]["reader_evidence"]["customer_email"] = "reader@example.invalid"
            private_receipt["sha256"] = hashlib.sha256(
                json.dumps(private_receipt["receipt"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            errors = MODULE._validate_w07_receipt_binding(private_receipt, repository, live)
            self.assertTrue(any("reader evidence must use the exact contract fields" in error for error in errors))
            self.assertTrue(any("private or credential material" in error for error in errors))

    def test_live_w07_receipt_reads_one_exact_authenticated_comment_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            receipt = binding["receipt"]
            assert isinstance(receipt, dict)
            program_result = subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "status": "pass",
                        "work_id": "PSP-P03-W07",
                        "receipt_url": binding["url"],
                        "receipt_sha256": binding["sha256"],
                    }
                ),
                "",
            )
            comment = {
                "user": {"login": next(iter(MODULE.PHASE_RECEIPT_AUTHORS))},
                "author_association": next(iter(MODULE.PHASE_RECEIPT_ASSOCIATIONS)),
                "body": "<!-- positioning-receipt:PSP-P03-W07 -->\n```json\n"
                + json.dumps(receipt, sort_keys=True)
                + "\n```",
            }
            with (
                mock.patch.object(MODULE, "_run_trusted_positioning_program", return_value=program_result),
                mock.patch.object(MODULE, "_fetch_github_issue_comment", return_value=comment),
            ):
                observed = MODULE._live_w07_verification(repository)
            self.assertEqual(live["authenticated_receipt"], observed["authenticated_receipt"])

            comment["body"] += "\n" + comment["body"]
            with (
                mock.patch.object(MODULE, "_run_trusted_positioning_program", return_value=program_result),
                mock.patch.object(MODULE, "_fetch_github_issue_comment", return_value=comment),
                self.assertRaisesRegex(ValueError, "exactly one marked work receipt"),
            ):
                MODULE._live_w07_verification(repository)

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
            self.assertTrue(any("observed-head aggregate" in error for error in errors))

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

    def test_w07_evidence_uses_only_the_isolated_canonical_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as caller_directory:
            source_repository = Path(source_directory)
            caller_repository = Path(caller_directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(source_repository, payload)
            binding, live = self._valid_w07_binding(source_repository, head, response_path, payload)
            receipt = binding["receipt"]
            assert isinstance(receipt, dict)
            evidence = receipt["reader_evidence"]
            assert isinstance(evidence, dict)
            memo_path = evidence["decision_memo_path"]
            assert isinstance(memo_path, str)
            self.fetch_canonical_limen_bindings_mock.reset_mock()
            with (
                mock.patch.object(
                    MODULE,
                    "_git_blob",
                    side_effect=AssertionError("caller object store must not supply W07 evidence"),
                ),
                mock.patch.object(
                    MODULE,
                    "_sanitized_ancestry",
                    side_effect=AssertionError("caller object store must not decide W07 ancestry"),
                ),
            ):
                self.assertEqual(
                    [],
                    MODULE._validate_w07_receipt_binding(
                        binding,
                        caller_repository,
                        live,
                        closure_head=head,
                    ),
                )
            self.fetch_canonical_limen_bindings_mock.assert_called_once_with(
                {
                    *((head, path) for path in MODULE.W07_REPLAY_PATHS),
                    (head, response_path),
                    (head, memo_path),
                },
                descendant_head=head,
            )

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

    def test_w07_receipt_binds_the_reexecuted_predicate_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            binding, live = self._valid_w07_binding(repository, head, response_path, payload)
            receipt = binding["receipt"]
            assert isinstance(receipt, dict)
            predicate = receipt["predicate"]
            assert isinstance(predicate, dict)
            predicate["output_sha256"] = "0" * 64
            digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            binding["sha256"] = digest
            live["receipt_sha256"] = digest
            errors = MODULE._validate_w07_receipt_binding(binding, repository, live)
        self.assertTrue(any("predicate output digest differs" in error for error in errors), errors)

    def test_w07_receipt_rejects_duplicate_response_members_before_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            payload = self._passing_w07_payload()
            head, response_path = self._w07_repository(repository, payload)
            response = repository / response_path
            raw = response.read_text(encoding="utf-8")
            marker = '"verbatim_notes": '
            self.assertIn(marker, raw)
            raw = raw.replace(marker, '"verbatim_notes": "private-reader@example.invalid",\n      ' + marker, 1)
            response.write_text(raw, encoding="utf-8")
            subprocess.run(["git", "add", response_path], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "duplicate response member"],
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
        self.assertTrue(any("duplicate JSON member: verbatim_notes" in error for error in errors), errors)

    def test_w07_receipt_replays_validator_and_workflow_as_one_observed_head_pair(self) -> None:
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
            self.assertTrue(any("observed-head W07 workflow did not reproduce" in error for error in errors))

    def test_program_binding_covers_all_p05_leaves(self) -> None:
        self.assertEqual(
            [f"PSP-P05-W0{index}" for index in range(1, 7)],
            [row["work_id"] for row in self.contract["program_binding"]["leaf_audit"]],
        )


if __name__ == "__main__":
    unittest.main()
