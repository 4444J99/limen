#!/usr/bin/env python3
"""Focused regression tests for the private PSP-C08 content controls."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "psp_c08_content.py"
SPEC = importlib.util.spec_from_file_location("psp_c08_content", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContentControlTests(unittest.TestCase):
    def copy_root(self) -> Path:
        sandbox = Path(tempfile.mkdtemp())
        target = sandbox / "repo"
        (target / "docs" / "positioning").mkdir(parents=True)
        shutil.copytree(ROOT / "docs" / "positioning" / "content", target / "docs" / "positioning" / "content")
        return target

    def test_current_package_validates(self) -> None:
        report = MODULE.validate(ROOT)
        self.assertEqual(report, {"assets": 8, "mode": "dry-run-only", "status": "ok"})

    def test_private_email_is_rejected(self) -> None:
        target = self.copy_root()
        path = target / "docs" / "positioning" / "content" / "content-control.json"
        control = json.loads(path.read_text(encoding="utf-8"))
        control["assets"][0]["draft"] += " private.person@example.com"
        path.write_text(json.dumps(control), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContentError, "email address"):
            MODULE.validate(target)

    def test_dry_run_cannot_claim_a_send(self) -> None:
        target = self.copy_root()
        path = target / "docs" / "positioning" / "content" / "dry-run-publication-package.json"
        package = json.loads(path.read_text(encoding="utf-8"))
        package["send_count"] = 1
        path.write_text(json.dumps(package), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContentError, "deterministic staged assets"):
            MODULE.validate(target)

    def test_dependency_binding_cannot_claim_closure(self) -> None:
        target = self.copy_root()
        path = target / "docs" / "positioning" / "content" / "dependency-bindings.json"
        bindings = json.loads(path.read_text(encoding="utf-8"))
        bindings["counts_as_closure"] = True
        path.write_text(json.dumps(bindings), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContentError, "without closure credit"):
            MODULE.validate(target)

    def test_dependency_bindings_exactly_match_accepted_source_and_main_receipts(self) -> None:
        path = ROOT / "docs" / "positioning" / "content" / "dependency-bindings.json"
        bindings = MODULE.load_json(path)
        self.assertEqual(MODULE.EXPECTED_DEPENDENCY_BINDINGS, bindings["bindings"])
        self.assertEqual(MODULE.ASSIGNMENT_POLICY, bindings["assignment_policy"])
        self.assertEqual(
            MODULE.expected_assignment_requirements(),
            bindings["assignment_requirements"],
        )

    def test_dependency_binding_rejects_unvalidated_extra_fields(self) -> None:
        target = self.copy_root()
        path = target / "docs" / "positioning" / "content" / "dependency-bindings.json"
        bindings = json.loads(path.read_text(encoding="utf-8"))
        bindings["bindings"][1]["authorization"] = "credential-shaped-unchecked-field"
        path.write_text(json.dumps(bindings), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContentError, "accepted source and integration receipts"):
            MODULE.validate(target)

    def test_dependency_binding_rejects_source_or_integration_drift(self) -> None:
        target = self.copy_root()
        path = target / "docs" / "positioning" / "content" / "dependency-bindings.json"
        bindings = json.loads(path.read_text(encoding="utf-8"))
        bindings["bindings"][2]["limen_integrated_main_head"] = "0" * 40
        path.write_text(json.dumps(bindings), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContentError, "accepted source and integration receipts"):
            MODULE.validate(target)

    def test_assignment_contract_is_runtime_derived_without_frozen_models(self) -> None:
        path = ROOT / "docs" / "positioning" / "content" / "dependency-bindings.json"
        bindings = MODULE.load_json(path)
        self.assertTrue(
            all(
                "model" not in assignment and "slug" not in assignment
                for assignment in bindings["assignment_requirements"].values()
            )
        )
        target = self.copy_root()
        changed_path = target / "docs" / "positioning" / "content" / "dependency-bindings.json"
        changed = json.loads(changed_path.read_text(encoding="utf-8"))
        changed["assignment_requirements"]["PSP-P09-W08"]["effort"] = "low"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContentError, "canonical runtime registry"):
            MODULE.validate(target)

    def test_duplicate_json_members_fail_closed(self) -> None:
        target = self.copy_root()
        path = target / "docs" / "positioning" / "content" / "dependency-bindings.json"
        raw = path.read_text(encoding="utf-8")
        path.write_text(
            raw.replace('"state": "PREPARED",', '"state": "hidden",\n  "state": "PREPARED",', 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MODULE.ContentError, "duplicate JSON member: state"):
            MODULE.validate(target)

    def test_expiry_logic_quarantines_old_copy(self) -> None:
        self.assertEqual(MODULE.freshness_state("2026-08-11", "2026-08-12"), "expired")


if __name__ == "__main__":
    unittest.main()
