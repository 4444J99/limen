#!/usr/bin/env python3
"""Adversarial tests for the PSP-P13-W03 technical-readiness audit."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "docs/positioning/foundry/psp-c11/verify_technical_readiness.py"
SPEC = importlib.util.spec_from_file_location("verify_technical_readiness", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TechnicalReadinessAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.audit = MODULE.load_json(MODULE.AUDIT)
        self.snapshot = MODULE.load_json(MODULE.SNAPSHOT)
        self.contract = MODULE.load_json(MODULE.CONTRACT)

    def errors(self, audit: dict | None = None) -> list[str]:
        return MODULE.validate_audit(audit or self.audit, self.snapshot, self.contract)

    def public_row(self, audit: dict | None = None, candidate_id: str | None = None) -> dict:
        value = audit or self.audit
        return next(
            row
            for row in value["candidates"]
            if row["visibility"] == "public" and (candidate_id is None or row["candidate_id"] == candidate_id)
        )

    def experiment_row(self, audit: dict | None = None) -> dict:
        candidate_id = next(
            row["candidate_id"]
            for row in self.snapshot["candidates"]
            if row["visibility"] == "public" and row["preflight_disposition"] == "experiment"
        )
        return self.public_row(audit, candidate_id)

    def private_row(self, audit: dict | None = None) -> dict:
        value = audit or self.audit
        return next(row for row in value["candidates"] if row["visibility"] == "private")

    @staticmethod
    def receipt_url(row: dict, dimension: str) -> str:
        receipt_slug = MODULE.DIMENSION_RECEIPT_TOKENS[dimension][0]
        return (
            f"https://github.com/{row['repository']}/blob/{'f' * 40}"
            f"/docs/receipts/technical-readiness/{receipt_slug}-receipt.json"
        )

    @staticmethod
    def evidence_receipt(row: dict, dimension: str, status: str = "pass") -> dict:
        output = f"{dimension}:{status}:output\n".encode("utf-8")
        artifact = f"{dimension}:{status}:artifact\n".encode("utf-8")
        receipt = {
            "schema_version": "limen.psp_p13_w03_technical_evidence.v2",
            "repository": row["repository"],
            "tested_commit": row["observed_head"],
            "dimension": dimension,
            "status": status,
            "exit_code": 0 if status == "pass" else 1,
            "provenance_url": f"https://github.com/{row['repository']}/actions/runs/1234",
            "predicate_path": f".github/workflows/{dimension}-technical-readiness.yml",
            "output_path": f"docs/receipts/technical-readiness/{dimension}-output.txt",
            "output_sha256": MODULE.hashlib.sha256(output).hexdigest(),
            "artifact_path": f"docs/receipts/technical-readiness/{dimension}-artifact.json",
            "artifact_sha256": MODULE.hashlib.sha256(artifact).hexdigest(),
            "observed_at": "2026-08-15T00:00:00Z",
            "external_effects": [],
        }
        if dimension == "maintenance" and status == "pass":
            receipt["maintenance_funded"] = True
        return receipt

    @staticmethod
    def resolved_evidence(receipt: dict) -> dict:
        dimension = receipt["dimension"]
        status = receipt["status"]
        return {
            "receipt": receipt,
            "receipt_repository": receipt["repository"],
            "receipt_commit": "f" * 40,
            "output_sha256": MODULE.hashlib.sha256(f"{dimension}:{status}:output\n".encode("utf-8")).hexdigest(),
            "artifact_sha256": MODULE.hashlib.sha256(
                f"{dimension}:{status}:artifact\n".encode("utf-8")
            ).hexdigest(),
            "provenance": {
                "html_url": receipt["provenance_url"],
                "head_sha": receipt["tested_commit"],
                "status": "completed",
                "conclusion": "success" if status == "pass" else "failure",
                "path": receipt["predicate_path"],
                "run_started_at": "2026-08-14T23:59:00Z",
                "updated_at": receipt["observed_at"],
            },
        }

    def test_tracked_audit_is_valid_and_has_zero_effects(self) -> None:
        self.assertEqual([], self.errors())
        self.assertEqual([], self.audit["external_effects"])
        self.assertTrue(self.audit["owner_custody_unchanged"])
        self.assertEqual(62, self.audit["summary"]["candidate_count"])
        self.assertEqual({"public": 54, "private": 8}, self.audit["summary"]["visibility"])

    def test_duplicate_json_members_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"status":"safe","status":"shadowed"}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.AuditError, "duplicate JSON member: status"):
                MODULE.load_json(path)

    def test_root_and_source_lock_are_exact(self) -> None:
        changed = copy.deepcopy(self.audit)
        changed["extra"] = "credential-like-surplus"
        self.assertEqual(["audit must use the exact root schema"], self.errors(changed))
        changed = copy.deepcopy(self.audit)
        changed["source_lock"]["candidate_count"] = 61
        self.assertIn("audit source_lock drift", self.errors(changed))

    def test_top_level_observation_cannot_be_future_dated(self) -> None:
        changed = copy.deepcopy(self.audit)
        changed["observed_at"] = "9999-12-31T23:59:59Z"
        self.assertIn(
            "audit observed_at must be a non-future RFC3339 UTC timestamp",
            self.errors(changed),
        )

    def test_candidate_denominator_and_identity_are_exact(self) -> None:
        changed = copy.deepcopy(self.audit)
        changed["candidates"].pop()
        self.assertTrue(any("candidate count drift" in error for error in self.errors(changed)))
        changed = copy.deepcopy(self.audit)
        changed["candidates"].append(copy.deepcopy(changed["candidates"][0]))
        self.assertTrue(any("identity set or order drift" in error for error in self.errors(changed)))
        changed = copy.deepcopy(self.audit)
        changed["candidates"][0]["candidate_id"] = changed["candidates"][1]["candidate_id"]
        self.assertTrue(any("identity set or order drift" in error for error in self.errors(changed)))

    def test_candidate_projection_and_live_identity_digests_are_recomputed(self) -> None:
        changed_snapshot = copy.deepcopy(self.snapshot)
        changed_audit = copy.deepcopy(self.audit)
        changed_snapshot["candidates"][0]["candidate_id"] = "invented-candidate"
        changed_audit["candidates"][0]["candidate_id"] = "invented-candidate"
        errors = MODULE.validate_audit(changed_audit, changed_snapshot, self.contract)
        self.assertIn("accepted candidate projection digest drift", errors)
        errors = MODULE.validate_audit(
            self.audit,
            self.snapshot,
            self.contract,
            live_candidate_identity_sha256="0" * 64,
        )
        self.assertIn("live accepted candidate identity digest drift", errors)
        changed_snapshot = copy.deepcopy(self.snapshot)
        first_public = next(row for row in changed_snapshot["candidates"] if row["visibility"] == "public")
        second_public = next(
            row for row in changed_snapshot["candidates"] if row["visibility"] == "public" and row is not first_public
        )
        first_public["repository"] = second_public["repository"]
        errors = MODULE.validate_audit(self.audit, changed_snapshot, self.contract)
        self.assertTrue(
            any("duplicate repositories" in error or "projection digest drift" in error for error in errors)
        )

    def test_candidate_projection_digest_binds_lifecycle_fields(self) -> None:
        changed_snapshot = copy.deepcopy(self.snapshot)
        row = next(candidate for candidate in changed_snapshot["candidates"] if candidate["visibility"] == "public")
        row["current_state"] = "archived"
        row["preflight_disposition"] = "experiment"
        with self.assertRaisesRegex(MODULE.AuditError, "accepted public candidate lifecycle binding is invalid"):
            MODULE.candidate_projection_digest(changed_snapshot)

    def test_w01_acceptance_is_recomputed_and_live_receipt_is_bound(self) -> None:
        self.assertEqual(MODULE.SOURCE_LOCK["w01_acceptance_sha256"], MODULE.accepted_w01_acceptance_digest())
        receipt = {
            "acceptance_sha256": MODULE.SOURCE_LOCK["w01_acceptance_sha256"],
            "observed_heads": {"organvm/limen": MODULE.SOURCE_LOCK["w01_accepted_head"]},
        }
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        verification = {
            "status": "pass",
            "work_id": "PSP-P13-W01",
            "receipt_url": MODULE.SOURCE_LOCK["w01_receipt"],
            "receipt_sha256": MODULE.hashlib.sha256(canonical).hexdigest(),
        }
        comment = {
            "html_url": MODULE.SOURCE_LOCK["w01_receipt"],
            "body": "<!-- positioning-receipt:PSP-P13-W01 -->\n```json\n" + json.dumps(receipt) + "\n```",
        }
        with mock.patch.object(MODULE, "_run_json", side_effect=[verification, comment]):
            MODULE.verify_w01_live_receipt()
        receipt["acceptance_sha256"] = "0" * 64
        comment["body"] = "<!-- positioning-receipt:PSP-P13-W01 -->\n```json\n" + json.dumps(receipt) + "\n```"
        with (
            mock.patch.object(MODULE, "_run_json", side_effect=[verification, comment]),
            self.assertRaisesRegex(MODULE.AuditError, "binding drifted"),
        ):
            MODULE.verify_w01_live_receipt()

    def test_public_head_and_live_head_are_exact(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["observed_head"] = "not-a-head"
        self.assertTrue(any("40-hex commit" in error for error in self.errors(changed)))
        heads = {
            row["repository"]: row["observed_head"] for row in self.audit["candidates"] if row["visibility"] == "public"
        }
        first_repository = self.public_row()["repository"]
        heads[first_repository] = "0" * 40
        errors = MODULE.validate_audit(
            self.audit,
            self.snapshot,
            self.contract,
            live_heads=heads,
        )
        self.assertTrue(any("observed_head drifted live" in error for error in errors))

    def test_verified_results_require_immutable_receipt_evidence(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["build"] = {"state": "verified_pass", "evidence_url": "https://github.com/example/repo/actions/runs/1"}
        self.assertTrue(any("dimension-specific immutable technical receipt" in error for error in self.errors(changed)))
        row["build"]["evidence_url"] = f"https://example.invalid/default_branch/{row['observed_head']}"
        self.assertTrue(any("metadata as technical proof" in error for error in self.errors(changed)))

    def test_generic_commit_url_cannot_prove_any_technical_dimension(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        build_receipt = self.receipt_url(row, "build")
        self.assertTrue(MODULE._url_proves_dimension(build_receipt, row["observed_head"], row["repository"], "build"))
        self.assertFalse(MODULE._url_proves_dimension(build_receipt, row["observed_head"], row["repository"], "test"))
        generic = f"https://github.com/{row['repository']}/commit/{row['observed_head']}"
        for dimension in (
            "build",
            "test",
            "deploy",
            "documentation",
            "data_custody",
            "ip_custody",
            "observability_return",
        ):
            row[dimension] = {"state": "verified_pass", "evidence_url": generic}
        row["security"] = {"class": "low", "state": "verified_pass", "evidence_url": generic}
        row["maintenance"] = {
            "state": "verified_pass",
            "owner": "maintainer",
            "estimate_hours_per_month": 1,
            "evidence_url": generic,
            "funding_evidence_url": generic,
            "blocker": None,
        }
        errors = self.errors(changed)
        self.assertGreaterEqual(
            sum("dimension-specific immutable technical receipt" in error for error in errors),
            len(MODULE.DIMENSION_RECEIPT_TOKENS),
        )

    def test_live_verified_evidence_requires_resolved_receipt_contents(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["build"] = {
            "state": "verified_pass",
            "evidence_url": self.receipt_url(row, "build"),
        }
        errors = MODULE.validate_audit(changed, self.snapshot, self.contract, live_receipts={})
        self.assertTrue(any("must resolve immutable output and artifact evidence" in error for error in errors))
        self.assertEqual(
            [],
            MODULE._evidence_receipt_errors(
                self.resolved_evidence(self.evidence_receipt(row, "build")),
                row["repository"],
                row["observed_head"],
                "build",
                "verified_pass",
                "candidate.build",
            ),
        )
        receipt = self.evidence_receipt(row, "build")
        output = b"build:pass:output\n"
        artifact = b"build:pass:artifact\n"
        resolved = self.resolved_evidence(receipt)
        with mock.patch.object(
            MODULE, "_fetch_exact_head_blob", return_value=json.dumps(receipt).encode("utf-8")
        ), mock.patch.object(
            MODULE, "_fetch_repository_blob", side_effect=[output, artifact]
        ), mock.patch.object(MODULE, "_run_json", return_value=resolved["provenance"]):
            receipts = MODULE.collect_live_evidence_receipts(changed)
        self.assertEqual(resolved, receipts[(row["candidate_id"], "build")])
        broken = self.evidence_receipt(row, "build")
        broken["exit_code"] = 1
        self.assertIn(
            "candidate.build live receipt exit_code drift",
            MODULE._evidence_receipt_errors(
                self.resolved_evidence(broken),
                row["repository"],
                row["observed_head"],
                "build",
                "verified_pass",
                "candidate.build",
            ),
        )
        broken = self.evidence_receipt(row, "build")
        broken["output_sha256"] = "0" * 64
        self.assertIn(
            "candidate.build live receipt must bind independently distinct output and artifact evidence",
            MODULE._evidence_receipt_errors(
                self.resolved_evidence(broken),
                row["repository"],
                row["observed_head"],
                "build",
                "verified_pass",
                "candidate.build",
            ),
        )

    def test_live_receipt_requires_trusted_result_semantics_and_distinct_artifacts(self) -> None:
        row = self.public_row()
        receipt = self.evidence_receipt(row, "build")
        resolved = self.resolved_evidence(receipt)
        resolved["provenance"]["conclusion"] = "failure"
        self.assertTrue(
            any(
                "trusted result semantics drift" in error
                for error in MODULE._evidence_receipt_errors(
                    resolved,
                    row["repository"],
                    row["observed_head"],
                    "build",
                    "verified_pass",
                    "candidate.build",
                )
            )
        )
        receipt = self.evidence_receipt(row, "build")
        receipt["artifact_path"] = receipt["output_path"]
        receipt["artifact_sha256"] = receipt["output_sha256"]
        resolved = self.resolved_evidence(receipt)
        resolved["artifact_sha256"] = resolved["output_sha256"]
        errors = MODULE._evidence_receipt_errors(
            resolved,
            row["repository"],
            row["observed_head"],
            "build",
            "verified_pass",
            "candidate.build",
        )
        self.assertTrue(any("distinct safe output and artifact paths" in error for error in errors))
        self.assertTrue(any("independently distinct output and artifact evidence" in error for error in errors))

        receipt = self.evidence_receipt(row, "maintenance")
        receipt["maintenance_funded"] = False
        self.assertIn(
            "candidate.maintenance live receipt must prove funded maintenance",
            MODULE._evidence_receipt_errors(
                self.resolved_evidence(receipt),
                row["repository"],
                row["observed_head"],
                "maintenance",
                "verified_pass",
                "candidate.maintenance",
            ),
        )

    def test_live_collection_has_one_deadline_call_budget_and_response_cache(self) -> None:
        response = mock.Mock(returncode=0, stdout='{"status":"pass"}')
        collection = MODULE.LiveCollection(deadline_seconds=10, call_limit=1, clock=lambda: 0)
        with mock.patch.object(MODULE.subprocess, "run", return_value=response) as run:
            first = MODULE._run_json(["gh", "api", "immutable"], collection=collection)
            second = MODULE._run_json(["gh", "api", "immutable"], collection=collection)
            self.assertEqual(first, second)
            self.assertEqual(1, run.call_count)
            self.assertEqual(10, run.call_args.kwargs["timeout"])
            with self.assertRaisesRegex(MODULE.AuditError, "collection budget exhausted"):
                MODULE._run_json(["gh", "api", "another"], collection=collection)

        ticks = iter((0, 11))
        expired = MODULE.LiveCollection(deadline_seconds=10, call_limit=2, clock=lambda: next(ticks))
        with self.assertRaisesRegex(MODULE.AuditError, "collection budget exhausted"):
            MODULE._run_json(["gh", "api", "expired"], collection=expired)

    def test_live_receipt_rejects_future_chronology_and_allows_later_receipt_commit(self) -> None:
        row = self.public_row()
        receipt = self.evidence_receipt(row, "deploy")
        self.assertNotEqual(row["observed_head"], "f" * 40)
        self.assertTrue(MODULE._url_proves_dimension(self.receipt_url(row, "deploy"), row["observed_head"], row["repository"], "deploy"))
        receipt["observed_at"] = "9999-12-31T23:59:59Z"
        resolved = self.resolved_evidence(receipt)
        self.assertTrue(
            any(
                "chronology drift" in error
                for error in MODULE._evidence_receipt_errors(
                    resolved,
                    row["repository"],
                    row["observed_head"],
                    "deploy",
                    "verified_pass",
                    "candidate.deploy",
                )
            )
        )

    def test_live_receipt_exit_semantics_reject_bools_and_accept_any_nonzero_failure(self) -> None:
        row = self.public_row()
        failed = self.evidence_receipt(row, "test", "fail")
        failed["exit_code"] = 124
        self.assertEqual(
            [],
            MODULE._evidence_receipt_errors(
                self.resolved_evidence(failed),
                row["repository"],
                row["observed_head"],
                "test",
                "verified_fail",
                "candidate.test",
            ),
        )
        for state, status, exit_code in (("verified_pass", "pass", False), ("verified_fail", "fail", True)):
            receipt = self.evidence_receipt(row, "test", status)
            receipt["exit_code"] = exit_code
            self.assertIn(
                "candidate.test live receipt exit_code drift",
                MODULE._evidence_receipt_errors(
                    self.resolved_evidence(receipt),
                    row["repository"],
                    row["observed_head"],
                    "test",
                    state,
                    "candidate.test",
                ),
            )

    def test_readiness_model_requires_unique_dimensions_and_exactly_100_points(self) -> None:
        duplicate = copy.deepcopy(self.contract)
        duplicate["readiness_model"]["dimensions"].append(
            copy.deepcopy(duplicate["readiness_model"]["dimensions"][0])
        )
        with self.assertRaisesRegex(MODULE.AuditError, "duplicate dimensions"):
            MODULE.readiness_weights(duplicate)
        underweight = copy.deepcopy(self.contract)
        next(
            row for row in underweight["readiness_model"]["dimensions"] if row["id"] == "deploy_runtime"
        )["weight"] = 0
        with self.assertRaisesRegex(MODULE.AuditError, "dimension set or build/test allocation drifted"):
            MODULE.readiness_weights(underweight)

    def test_transfer_threshold_is_derived_and_validated_from_contract(self) -> None:
        self.assertEqual(75, MODULE.readiness_transfer_threshold(self.contract))
        changed = copy.deepcopy(self.contract)
        changed["economics_and_kill_rules"]["transfer_floor"]["technical_readiness_minimum"] = 85
        self.assertEqual(85, MODULE.readiness_transfer_threshold(changed))
        changed["economics_and_kill_rules"]["transfer_floor"]["technical_readiness_minimum"] = True
        with self.assertRaisesRegex(MODULE.AuditError, "transfer threshold is invalid"):
            MODULE.readiness_transfer_threshold(changed)

    def test_maintenance_maximum_is_contract_derived_and_bounded(self) -> None:
        self.assertEqual(40, MODULE.readiness_maintenance_maximum(self.contract))
        changed = copy.deepcopy(self.contract)
        changed["readiness_model"]["maintenance_estimate_hours_per_month_maximum"] = 12
        self.assertEqual(12, MODULE.readiness_maintenance_maximum(changed))
        changed["readiness_model"]["maintenance_estimate_hours_per_month_maximum"] = 1_000
        with self.assertRaisesRegex(MODULE.AuditError, "maintenance estimate maximum is invalid"):
            MODULE.readiness_maintenance_maximum(changed)

    def test_all_hard_floors_can_pass_with_empty_blockers(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.experiment_row(changed)
        for dimension in (
            "build",
            "test",
            "deploy",
            "documentation",
            "data_custody",
            "ip_custody",
            "observability_return",
        ):
            row[dimension] = {
                "state": "verified_pass",
                "evidence_url": self.receipt_url(row, dimension),
            }
        row["security"] = {
            "class": "low",
            "state": "verified_pass",
            "evidence_url": self.receipt_url(row, "security"),
        }
        row["maintenance"] = {
            "state": "verified_pass",
            "owner": "maintainer",
            "estimate_hours_per_month": 1,
            "evidence_url": self.receipt_url(row, "maintenance"),
            "funding_evidence_url": self.receipt_url(row, "maintenance"),
            "blocker": None,
        }
        row["readiness_score"] = 100
        row["blockers"] = []
        row["transfer_eligible"] = True
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        self.assertEqual([], self.errors(changed))

        row["maintenance"].pop("funding_evidence_url")
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        errors = self.errors(changed)
        self.assertTrue(any("maintenance must use the exact dimension schema" in error for error in errors))
        self.assertTrue(any("transfer_eligible drift" in error for error in errors))

    def test_contract_hard_floors_allow_75_with_owned_nonhard_gaps(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.experiment_row(changed)
        for dimension in ("build", "test", "data_custody", "ip_custody", "observability_return"):
            row[dimension] = {
                "state": "verified_pass",
                "evidence_url": self.receipt_url(row, dimension),
            }
        row["security"] = {
            "class": "low",
            "state": "verified_pass",
            "evidence_url": self.receipt_url(row, "security"),
        }
        row["maintenance"] = {
            "state": "verified_pass",
            "owner": "maintainer",
            "estimate_hours_per_month": 1,
            "evidence_url": self.receipt_url(row, "maintenance"),
            "funding_evidence_url": self.receipt_url(row, "maintenance"),
            "blocker": None,
        }
        row["readiness_score"] = 75
        row["blockers"] = [
            blocker
            for blocker in row["blockers"]
            if blocker["code"] in {"deploy_evidence_missing", "documentation_evidence_missing"}
        ]
        row["transfer_eligible"] = True
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        self.assertEqual([], self.errors(changed))
        higher_floor = copy.deepcopy(self.contract)
        higher_floor["economics_and_kill_rules"]["transfer_floor"]["technical_readiness_minimum"] = 85
        self.assertTrue(
            any(
                "transfer_eligible drift" in error
                for error in MODULE.validate_audit(changed, self.snapshot, higher_floor)
            )
        )

    def test_blocker_predicate_is_executable_and_candidate_bound(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        blocker = row["blockers"][0]
        self.assertIn(f"--require-cleared {row['candidate_id']}:{blocker['code']}", blocker["predicate"])
        self.assertEqual(
            ["required blocker remains uncleared"],
            MODULE.required_blocker_errors(changed, f"{row['candidate_id']}:{blocker['code']}"),
        )
        blocker["predicate"] = "true"
        self.assertTrue(any("exact trusted live clearance command" in error for error in self.errors(changed)))

    def test_unproved_state_promotion_and_score_tamper_fail(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["deploy"]["state"] = "verified_pass"
        row["readiness_score"] = 100
        errors = self.errors(changed)
        self.assertTrue(any("candidate" in error and "deploy" in error and "immutable technical receipt" in error for error in errors))
        self.assertTrue(any("readiness_score drift" in error for error in errors))

    def test_joint_build_test_dimension_scores_only_when_both_pass(self) -> None:
        weights = MODULE.readiness_weights(self.contract)
        states = {dimension: "blocked_unverified" for dimension in weights}
        states["build"] = "verified_pass"
        self.assertEqual(0, MODULE.readiness_score(states, weights))
        states["test"] = "verified_pass"
        self.assertEqual(20, MODULE.readiness_score(states, weights))

    def test_security_and_custody_shapes_fail_closed(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["security"]["class"] = "unknown"
        row["data_custody"]["unexpected"] = "plaintext"
        row["ip_custody"]["state"] = ["verified_pass"]
        errors = self.errors(changed)
        self.assertTrue(any("security.class is invalid" in error for error in errors))
        self.assertTrue(any("data_custody must use the exact" in error for error in errors))
        self.assertTrue(any("ip_custody.state is invalid" in error for error in errors))

    def test_unsafe_security_classes_cannot_pass_or_satisfy_the_hard_floor(self) -> None:
        for security_class in ("high", "critical"):
            changed = copy.deepcopy(self.audit)
            row = self.public_row(changed)
            row["security"] = {
                "class": security_class,
                "state": "verified_pass",
                "evidence_url": self.receipt_url(row, "security"),
            }
            row["readiness_score"] = 15
            row["blockers"] = [
                blocker for blocker in row["blockers"] if blocker["code"] != "security_evidence_missing"
            ]
            changed["summary"] = MODULE.compute_summary(changed["candidates"])
            errors = self.errors(changed)
            self.assertTrue(any("verified_pass requires a low or moderate class" in error for error in errors))
            self.assertTrue(any("exactly cover every unresolved dimension" in error for error in errors))
            self.assertTrue(any("readiness_score drift" in error for error in errors))

    def test_maintenance_requires_owner_or_owned_blocker(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["maintenance"]["blocker"] = None
        self.assertTrue(any("maintenance.blocker" in error for error in self.errors(changed)))
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["maintenance"] = {
            "state": "verified_pass",
            "owner": None,
            "estimate_hours_per_month": None,
            "evidence_url": f"https://github.com/{row['repository']}/commit/{row['observed_head']}",
            "funding_evidence_url": f"https://github.com/{row['repository']}/commit/{row['observed_head']}",
            "blocker": None,
        }
        self.assertTrue(any("owner and bounded positive estimate" in error for error in self.errors(changed)))

    def test_maintenance_points_require_an_estimate_within_the_contract_maximum(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["maintenance"] = {
            "state": "verified_pass",
            "owner": "maintainer",
            "estimate_hours_per_month": 41,
            "evidence_url": self.receipt_url(row, "maintenance"),
            "funding_evidence_url": self.receipt_url(row, "maintenance"),
            "blocker": None,
        }
        row["readiness_score"] = 5
        row["blockers"] = [
            blocker for blocker in row["blockers"] if blocker["code"] != "maintenance_evidence_missing"
        ]
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        errors = self.errors(changed)
        self.assertTrue(any("estimate exceeds the contract maximum" in error for error in errors))
        self.assertTrue(any("readiness_score drift" in error for error in errors))
        self.assertTrue(any("exactly cover every unresolved dimension" in error for error in errors))

    def test_unresolved_maintenance_blocker_must_equal_canonical_copy(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["maintenance"]["blocker"]["owner"] = "contradictory-owner"
        errors = self.errors(changed)
        self.assertTrue(any("must equal the canonical top-level maintenance blocker" in error for error in errors))

    def test_summary_and_blocker_distribution_are_recomputed(self) -> None:
        changed = copy.deepcopy(self.audit)
        changed["summary"]["transfer_eligible"] = 1
        self.assertIn("audit summary drift", self.errors(changed))
        changed = copy.deepcopy(self.audit)
        self.public_row(changed)["blockers"][0]["owner"] = "unowned"
        self.assertIn("audit summary drift", self.errors(changed))

    def test_duplicate_blockers_and_transfer_with_hard_blocker_fail(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["blockers"].append(copy.deepcopy(row["blockers"][0]))
        row["transfer_eligible"] = True
        errors = self.errors(changed)
        self.assertTrue(any("blocker codes must be unique" in error for error in errors))
        self.assertTrue(any("cannot be transferable" in error for error in errors))

        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["blockers"] = row["blockers"][1:]
        self.assertTrue(any("exactly cover every unresolved dimension" in error for error in self.errors(changed)))

    def test_not_applicable_dimensions_retain_owned_blockers(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["documentation"] = {"state": "not_applicable", "evidence_url": None}
        row["blockers"] = [
            blocker for blocker in row["blockers"] if blocker["code"] != "documentation_evidence_missing"
        ]
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        self.assertTrue(any("exactly cover every unresolved dimension" in error for error in self.errors(changed)))

    def test_blocker_codes_are_shell_safe_and_unclassified_codes_block_transfer(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        injected = MODULE._blocker(row["candidate_id"], "note; touch /tmp/owned #", "unsafe")
        row["blockers"].append(injected)
        errors = self.errors(changed)
        self.assertTrue(any("safe lowercase identifier" in error for error in errors))
        self.assertTrue(any("exactly cover every unresolved dimension" in error for error in errors))

        changed = copy.deepcopy(self.audit)
        row = self.experiment_row(changed)
        for dimension in (
            "build",
            "test",
            "deploy",
            "documentation",
            "data_custody",
            "ip_custody",
            "observability_return",
        ):
            row[dimension] = {"state": "verified_pass", "evidence_url": self.receipt_url(row, dimension)}
        row["security"] = {
            "class": "low",
            "state": "verified_pass",
            "evidence_url": self.receipt_url(row, "security"),
        }
        row["maintenance"] = {
            "state": "verified_pass",
            "owner": "maintainer",
            "estimate_hours_per_month": 1,
            "evidence_url": self.receipt_url(row, "maintenance"),
            "funding_evidence_url": self.receipt_url(row, "maintenance"),
            "blocker": None,
        }
        row["readiness_score"] = 100
        row["blockers"] = [MODULE._blocker(row["candidate_id"], "credential_rotation_pending", "rotate")]
        row["transfer_eligible"] = True
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        errors = self.errors(changed)
        self.assertTrue(any("exactly cover every unresolved dimension" in error for error in errors))
        self.assertTrue(any("transfer_eligible drift" in error for error in errors))

    def test_accepted_archived_and_parked_candidates_never_transfer(self) -> None:
        archived_id = next(
            row["candidate_id"]
            for row in self.snapshot["candidates"]
            if row["visibility"] == "public" and row["current_state"] == "archived"
        )
        parked_id = next(
            row["candidate_id"]
            for row in self.snapshot["candidates"]
            if row["visibility"] == "public"
            and row["current_state"] != "archived"
            and row["preflight_disposition"] == "park"
        )
        for candidate_id in (archived_id, parked_id):
            changed = copy.deepcopy(self.audit)
            row = self.public_row(changed, candidate_id)
            for dimension in (
                "build",
                "test",
                "deploy",
                "documentation",
                "data_custody",
                "ip_custody",
                "observability_return",
            ):
                row[dimension] = {
                    "state": "verified_pass",
                    "evidence_url": self.receipt_url(row, dimension),
                }
            row["security"] = {
                "class": "low",
                "state": "verified_pass",
                "evidence_url": self.receipt_url(row, "security"),
            }
            row["maintenance"] = {
                "state": "verified_pass",
                "owner": "maintainer",
                "estimate_hours_per_month": 1,
                "evidence_url": self.receipt_url(row, "maintenance"),
                "funding_evidence_url": self.receipt_url(row, "maintenance"),
                "blocker": None,
            }
            row["readiness_score"] = 100
            row["blockers"] = []
            row["transfer_eligible"] = True
            changed["summary"] = MODULE.compute_summary(changed["candidates"])
            self.assertTrue(any("archived or parked lifecycle" in error for error in self.errors(changed)))

    def test_unhashable_candidate_fields_fail_closed(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["candidate_id"] = {"shadow": "identity"}
        row["visibility"] = ["public"]
        row["readiness_score"] = {"score": 0}
        errors = self.errors(changed)
        self.assertTrue(any("identity set or order drift" in error for error in errors))
        self.assertIn("audit summary drift", errors)

    def test_private_rows_are_opaque_and_coarse(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.private_row(changed)
        row["repository"] = "private/name"
        self.assertTrue(any("exact private row schema" in error for error in self.errors(changed)))
        changed = copy.deepcopy(self.audit)
        row = self.private_row(changed)
        row["blocker"]["owner"] = "named-person"
        self.assertTrue(any("generic accountable owner role" in error for error in self.errors(changed)))

    def test_private_clearance_is_deferred_until_trusted_live_custody_validation(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.private_row(changed)
        candidate_id = row["candidate_id"]
        digest = "a" * 64
        row["readiness_status"] = "clearance_pending_live"
        row["clearance_receipt_sha256"] = digest
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        self.assertEqual([], self.errors(changed))
        self.assertEqual(
            ["required blocker remains uncleared"],
            MODULE.required_blocker_errors(changed, f"{candidate_id}:restricted_private_evidence"),
        )
        errors = MODULE.validate_audit(
            changed,
            self.snapshot,
            self.contract,
            private_clearance_receipts={},
        )
        self.assertTrue(any("owner-controlled custody" in error for error in errors))
        self.assertEqual(
            [],
            MODULE.validate_audit(
                changed,
                self.snapshot,
                self.contract,
                private_clearance_receipts={candidate_id: digest},
            ),
        )
        self.assertEqual([], MODULE.validate_audit(changed, self.snapshot, self.contract, private_clearance_receipts=None))
        changed = copy.deepcopy(changed)
        row = self.private_row(changed)
        row["readiness_status"] = "cleared"
        row["blocker"] = None
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        self.assertTrue(any("private status drift" in error for error in self.errors(changed)))

    def test_live_refresh_preserves_only_unchanged_head_evidence(self) -> None:
        previous = copy.deepcopy(self.audit)
        row = self.public_row(previous)
        row["build"] = {"state": "verified_pass", "evidence_url": self.receipt_url(row, "build")}
        row["blockers"] = [blocker for blocker in row["blockers"] if blocker["code"] != "build_evidence_missing"]
        previous["summary"] = MODULE.compute_summary(previous["candidates"])
        heads = {
            candidate["repository"]: candidate["observed_head"]
            for candidate in self.audit["candidates"]
            if candidate["visibility"] == "public"
        }
        refreshed = MODULE.build_audit(self.snapshot, heads, "2026-08-15T00:00:00Z", previous)
        self.assertEqual("verified_pass", self.public_row(refreshed, row["candidate_id"])["build"]["state"])
        heads[row["repository"]] = "0" * 40
        refreshed = MODULE.build_audit(self.snapshot, heads, "2026-08-15T00:00:01Z", previous)
        reset = self.public_row(refreshed, row["candidate_id"])
        self.assertEqual("blocked_unverified", reset["build"]["state"])
        self.assertTrue(any(blocker["code"] == "build_evidence_missing" for blocker in reset["blockers"]))

    def test_private_identity_leak_is_fail_closed_without_disclosure(self) -> None:
        errors = MODULE.validate_audit(
            self.audit,
            self.snapshot,
            self.contract,
            private_leaks=["docs/positioning/foundry/psp-c11/README.md"],
        )
        self.assertIn("private repository identity leaked into public C11 paths", errors)

    def test_private_identity_scan_is_case_insensitive_and_scans_path_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            path_leak = package / "SeCrEtRePo" / "notes.md"
            path_leak.parent.mkdir()
            path_leak.write_text("safe body", encoding="utf-8")
            content_leak = package / "safe.md"
            content_leak.write_text(
                "git clone https://github.com/OwNeR/SeCrEtRePo.git\n"
                "git clone git@github.com:OwNeR/SeCrEtRePo.git\n",
                encoding="utf-8",
            )
            tracked_file = package / "tracked.md"
            tracked_file.write_text("owner/secretrepo", encoding="utf-8")
            with mock.patch.object(MODULE, "PACKAGE", package), mock.patch.object(MODULE, "ROOT", package), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="safe.md\ntracked.md\n"),
            ):
                leaks = MODULE._private_identity_leaks({"owner/SecretRepo"}, {"SecretRepo"})
            self.assertEqual(["safe.md", "tracked.md"], leaks)

    def test_generic_private_bare_name_in_prose_is_not_an_identity_leak(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            tracked = package / "tracked.md"
            tracked.write_text("The public status remains restricted.\n", encoding="utf-8")
            with mock.patch.object(MODULE, "PACKAGE", package), mock.patch.object(MODULE, "ROOT", package), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="tracked.md\n"),
            ):
                leaks = MODULE._private_identity_leaks({"owner/status"}, {"status"})
            self.assertEqual([], leaks)

    def test_private_identity_tracked_path_listing_times_out_fail_closed(self) -> None:
        with mock.patch.object(
            MODULE.subprocess,
            "run",
            side_effect=MODULE.subprocess.TimeoutExpired(["git", "ls-files"], 240),
        ):
            with self.assertRaisesRegex(MODULE.AuditError, "path listing timed out"):
                MODULE._private_identity_leaks(set(), set())

    def test_pr_gate_runs_static_handoff_and_public_evidence_while_private_live_is_operator_only(self) -> None:
        registry = yaml.safe_load((ROOT / "institutio/governance/gates.yaml").read_text(encoding="utf-8"))
        static = registry["gates"]["positioning-foundry-technical-readiness-test"]
        public_live = registry["gates"]["positioning-foundry-technical-readiness-public-live"]
        live = registry["gates"]["positioning-foundry-technical-readiness-live"]
        owning_paths = {
            "docs/positioning/foundry/psp-c11/technical-readiness-audit.json",
            "docs/positioning/foundry/psp-c11/test_technical_readiness.py",
            "docs/positioning/foundry/psp-c11/verify_technical_readiness.py",
            "scripts/positioning-foundry-preflight.py",
            "scripts/tests/test_positioning_foundry_handoff.py",
        }
        self.assertTrue(owning_paths.issubset(static["paths"]))
        public_paths = owning_paths - {
            "docs/positioning/foundry/psp-c11/test_technical_readiness.py",
            "scripts/positioning-foundry-preflight.py",
            "scripts/tests/test_positioning_foundry_handoff.py",
        }
        self.assertTrue(public_paths <= set(public_live["paths"]))
        self.assertTrue(
            owning_paths
            - {
                "docs/positioning/foundry/psp-c11/test_technical_readiness.py",
                "scripts/tests/test_positioning_foundry_handoff.py",
            }
            <= set(live["paths"])
        )
        self.assertNotIn("--live", static["command"])
        self.assertIn("test_technical_readiness.py", static["command"])
        self.assertIn("test_positioning_foundry_handoff.py", static["command"])
        self.assertIn("verify_technical_readiness.py", static["command"])
        self.assertIn("--public-live", public_live["command"].split())
        self.assertNotIn("--live", public_live["command"].split())
        self.assertIsNot(public_live.get("scoped"), False)
        self.assertIs(live["scoped"], False)
        self.assertIn("--live", live["command"].split())
        self.assertNotIn("ci_job", live)
        whole = (ROOT / "scripts/verify-whole.sh").read_text(encoding="utf-8")
        self.assertIn('if [[ "${LIMEN_VERIFY_LIVE:-0}" == "1" ]]', whole)
        self.assertIn(live["command"], whole)

    def test_public_live_mode_never_collects_private_operator_context(self) -> None:
        argv = [str(SCRIPT), "--public-live", "--json"]
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(MODULE, "collect_public_heads") as collect_public_heads,
            mock.patch.object(MODULE, "verify_w01_live_receipt") as verify_w01,
            mock.patch.object(MODULE, "collect_live_evidence_receipts", return_value={}) as collect_receipts,
            mock.patch.object(MODULE, "collect_live_context", side_effect=AssertionError("private census invoked")),
            mock.patch.object(
                MODULE,
                "load_private_clearance_receipts",
                side_effect=AssertionError("private custody invoked"),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            result = MODULE.main()
        collect_public_heads.assert_not_called()
        self.assertIs(verify_w01.call_args.args[0], collect_receipts.call_args.args[1])
        self.assertEqual(0, result)
        self.assertEqual("pass", json.loads(stdout.getvalue())["status"])

    def test_invalid_generated_live_audit_is_not_written(self) -> None:
        invalid = copy.deepcopy(self.audit)
        invalid["candidates"][0]["unexpected"] = "shape drift"
        heads = {
            row["repository"]: row["observed_head"] for row in self.audit["candidates"] if row["visibility"] == "public"
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "must-not-exist.json"
            argv = [str(SCRIPT), "--live", "--write", str(destination), "--json"]
            stdout = io.StringIO()
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    MODULE,
                    "collect_live_context",
                    return_value=(heads, [], MODULE.SOURCE_LOCK["candidate_identity_sha256"]),
                ),
                mock.patch.object(MODULE, "build_audit", return_value=invalid),
                contextlib.redirect_stdout(stdout),
            ):
                result = MODULE.main()
            self.assertEqual(1, result)
            self.assertFalse(destination.exists())
            self.assertEqual("fail", json.loads(stdout.getvalue())["status"])

    def test_validation_output_is_deterministic_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(json.dumps(self.audit), encoding="utf-8")
            before = path.read_bytes()
            argv = [str(SCRIPT), "--audit", str(path), "--json"]
            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
                result = MODULE.main()
            payload = json.loads(stdout.getvalue())
            self.assertEqual(0, result)
            self.assertEqual("pass", payload["status"])
            self.assertEqual([], payload["external_effects"])
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
