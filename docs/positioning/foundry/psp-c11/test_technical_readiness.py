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

    def public_row(self, audit: dict | None = None) -> dict:
        value = audit or self.audit
        return next(row for row in value["candidates"] if row["visibility"] == "public")

    def private_row(self, audit: dict | None = None) -> dict:
        value = audit or self.audit
        return next(row for row in value["candidates"] if row["visibility"] == "private")

    @staticmethod
    def receipt_url(row: dict, dimension: str) -> str:
        receipt_slug = MODULE.DIMENSION_RECEIPT_TOKENS[dimension][0]
        return (
            f"https://github.com/{row['repository']}/blob/{row['observed_head']}"
            f"/docs/receipts/technical-readiness/{receipt_slug}-receipt.json"
        )

    @staticmethod
    def evidence_receipt(row: dict, dimension: str, status: str = "pass") -> dict:
        return {
            "schema_version": "limen.psp_p13_w03_technical_evidence.v1",
            "repository": row["repository"],
            "commit": row["observed_head"],
            "dimension": dimension,
            "status": status,
            "observed_at": "2026-08-15T00:00:00Z",
            "command": f"verify-{dimension}",
            "external_effects": [],
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

    def test_verified_results_require_exact_head_evidence(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        row["build"] = {"state": "verified_pass", "evidence_url": "https://github.com/example/repo/actions/runs/1"}
        self.assertTrue(any("pinned to observed_head" in error for error in self.errors(changed)))
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
            "blocker": None,
        }
        errors = self.errors(changed)
        self.assertGreaterEqual(
            sum("dimension-specific exact-head technical receipt" in error for error in errors),
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
        self.assertTrue(any("live receipt must use the exact evidence schema" in error for error in errors))
        self.assertEqual(
            [],
            MODULE._evidence_receipt_errors(
                self.evidence_receipt(row, "build"),
                row["repository"],
                row["observed_head"],
                "build",
                "verified_pass",
                "candidate.build",
            ),
        )
        encoded = MODULE.base64.b64encode(json.dumps(self.evidence_receipt(row, "build")).encode("utf-8")).decode(
            "ascii"
        )
        with mock.patch.object(MODULE, "_run_json", return_value={"encoding": "base64", "content": encoded}):
            receipts = MODULE.collect_live_evidence_receipts(changed)
        self.assertEqual(self.evidence_receipt(row, "build"), receipts[(row["candidate_id"], "build")])

    def test_all_hard_floors_can_pass_with_empty_blockers(self) -> None:
        changed = copy.deepcopy(self.audit)
        row = self.public_row(changed)
        for dimension in (
            "build",
            "test",
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
            "blocker": None,
        }
        row["readiness_score"] = 75
        row["blockers"] = []
        row["transfer_eligible"] = True
        changed["summary"] = MODULE.compute_summary(changed["candidates"])
        self.assertEqual([], self.errors(changed))

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
        self.assertTrue(any("deploy evidence" in error for error in errors))
        self.assertTrue(any("readiness_score drift" in error for error in errors))

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
            "blocker": None,
        }
        self.assertTrue(any("owner and bounded positive estimate" in error for error in self.errors(changed)))

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
            content_leak.write_text("OwNeR/SeCrEtRePo", encoding="utf-8")
            with mock.patch.object(MODULE, "PACKAGE", package):
                leaks = MODULE._private_identity_leaks({"owner/SecretRepo"}, {"SecretRepo"})
            self.assertEqual(2, len(leaks))

    def test_pr_gate_is_static_and_live_acceptance_requires_operator_context(self) -> None:
        registry = yaml.safe_load((ROOT / "institutio/governance/gates.yaml").read_text(encoding="utf-8"))
        static = registry["gates"]["positioning-foundry-technical-readiness-test"]
        live = registry["gates"]["positioning-foundry-technical-readiness-live"]
        owning_paths = {
            "docs/positioning/foundry/psp-c11/technical-readiness-audit.json",
            "docs/positioning/foundry/psp-c11/test_technical_readiness.py",
            "docs/positioning/foundry/psp-c11/verify_technical_readiness.py",
            "scripts/positioning-foundry-preflight.py",
        }
        self.assertTrue(owning_paths.issubset(static["paths"]))
        self.assertTrue(
            owning_paths - {"docs/positioning/foundry/psp-c11/test_technical_readiness.py"} <= set(live["paths"])
        )
        self.assertNotIn("--live", static["command"])
        self.assertIn("test_technical_readiness.py", static["command"])
        self.assertIn("verify_technical_readiness.py", static["command"])
        self.assertIs(live["scoped"], False)
        self.assertIn("--live", live["command"])
        self.assertNotIn("ci_job", live)
        whole = (ROOT / "scripts/verify-whole.sh").read_text(encoding="utf-8")
        self.assertIn('if [[ "${LIMEN_VERIFY_LIVE:-0}" == "1" ]]', whole)
        self.assertIn(live["command"], whole)

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
