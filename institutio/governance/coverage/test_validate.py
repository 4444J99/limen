"""Synthetic regression tests; no private data or network access."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("coverage_validator", ROOT / "validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
NOW = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "registry.json").read_text())
        self.instance = json.loads((ROOT / "instance.example.json").read_text())

    def verified_row(self):
        row = self.instance["records"][0]
        row.update(applicability="active", service_state="verified",
                   accountable_owner_ref="synthetic:owner", delivery_provider_ref="synthetic:provider",
                   authority_ref="synthetic:consent")
        row["evidence"] = {k: {"ref": "synthetic:" + k,
            "observed_at": "2026-10-01T19:00:00Z", "valid_until": "2026-10-02T19:00:00Z"}
            for k in validator.REQUIRED_EVIDENCE}
        return row

    def errors(self):
        return validator.validate_instance(self.instance, self.catalog, NOW)

    def test_catalog(self):
        self.assertEqual(validator.validate_catalog(self.catalog), [])
        self.assertEqual(len(self.catalog["responsibilities"]), 25)

    def test_unknown_template_is_valid_not_coverage(self):
        self.assertEqual(self.errors(), [])
        self.assertTrue(all(r["service_state"] == "not_assessed" for r in self.instance["records"]))

    def test_duplicate_id(self):
        self.catalog["responsibilities"].append(deepcopy(self.catalog["responsibilities"][0]))
        self.assertTrue(validator.validate_catalog(self.catalog))

    def test_unknown_source(self):
        self.catalog["responsibilities"][0]["source_refs"] = ["missing"]
        self.assertTrue(validator.validate_catalog(self.catalog))

    def test_unknown_handoff(self):
        self.catalog["responsibilities"][0]["handoffs"] = ["IC-D999"]
        self.assertTrue(validator.validate_catalog(self.catalog))

    def test_catalog_cannot_claim_delivered_support(self):
        self.catalog["responsibilities"][0]["service_state"] = "verified"
        self.assertTrue(validator.validate_catalog(self.catalog))

    def test_no_implicit_activation(self):
        self.catalog["policy"]["runtime_activated"] = True
        self.assertTrue(validator.validate_catalog(self.catalog))

    def test_every_responsibility_dispositioned(self):
        self.instance["records"].pop()
        self.assertTrue(self.errors())

    def test_duplicate_instance_record(self):
        self.instance["records"].append(deepcopy(self.instance["records"][0]))
        self.assertTrue(self.errors())

    def test_verified_assertion_with_current_references(self):
        self.verified_row()
        self.assertEqual(self.errors(), [])

    def test_verified_requires_owner(self):
        self.verified_row()["accountable_owner_ref"] = None
        self.assertTrue(self.errors())

    def test_verified_requires_delivery_provider(self):
        self.verified_row()["delivery_provider_ref"] = None
        self.assertTrue(self.errors())

    def test_verified_requires_outcome(self):
        del self.verified_row()["evidence"]["outcome"]
        self.assertTrue(self.errors())

    def test_stale_evidence(self):
        self.verified_row()["evidence"]["outcome"]["valid_until"] = "2026-10-01T19:30:00Z"
        self.assertTrue(self.errors())

    def test_expiry_boundary_is_exclusive(self):
        self.verified_row()["evidence"]["outcome"]["valid_until"] = "2026-10-01T20:00:00Z"
        self.assertTrue(self.errors())

    def test_future_observation(self):
        self.verified_row()["evidence"]["outcome"]["observed_at"] = "2026-10-02T18:00:00Z"
        self.assertTrue(self.errors())

    def test_naive_timestamp(self):
        self.verified_row()["evidence"]["outcome"]["observed_at"] = "2026-10-01T19:00:00"
        self.assertTrue(self.errors())

    def test_contingent_is_not_delivered(self):
        self.verified_row()["applicability"] = "contingent"
        self.assertTrue(self.errors())

    def test_declined_requires_evidence(self):
        self.instance["records"][0]["applicability"] = "declined"
        self.assertTrue(self.errors())

    def test_explicit_approved_exclusion(self):
        row = self.instance["records"][0]
        row.update(applicability="declined", authority_ref="synthetic:consent",
                   disposition_reason="Synthetic person declined institutional involvement.")
        row["evidence"]["applicability"] = {"ref": "synthetic:decision",
            "observed_at": "2026-10-01T19:00:00Z", "valid_until": "2026-11-01T19:00:00Z"}
        self.assertEqual(self.errors(), [])

    def test_blocked_requires_blocker_reference(self):
        self.instance["records"][0]["service_state"] = "blocked"
        self.assertTrue(self.errors())

    def test_no_private_values_in_errors(self):
        self.instance["records"][0]["responsibility_id"] = "sensitive-value-not-for-output"
        self.assertNotIn("sensitive-value-not-for-output", str(self.errors()))

    def test_wrong_typed_state_is_reported(self):
        self.instance["records"][0]["applicability"] = []
        self.instance["records"][0]["service_state"] = {}
        self.assertTrue(self.errors())

    def test_dangling_legacy_term(self):
        self.catalog["legacy_term_crosswalk"]["consulting"] = "IC-P999"
        self.assertTrue(validator.validate_catalog(self.catalog))

    def test_cli_null_instance_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "null.json"
            path.write_text("null")
            run = subprocess.run([sys.executable, str(ROOT / "validate.py"), "--instance", str(path)],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 1)
        self.assertFalse(json.loads(run.stdout)["declarations_valid"])

    def test_cli(self):
        run = subprocess.run([sys.executable, str(ROOT / "validate.py"), "--instance",
            str(ROOT / "instance.example.json"), "--as-of", NOW.isoformat()],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        receipt = json.loads(run.stdout)
        self.assertFalse(receipt["service_delivery_certified"])
        self.assertFalse(receipt["evidence_payloads_verified"])
        self.assertEqual(receipt["service_state_counts"], {"not_assessed": 25})


if __name__ == "__main__":
    unittest.main()
