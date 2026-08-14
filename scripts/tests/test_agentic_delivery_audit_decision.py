#!/usr/bin/env python3
"""Focused regressions for the PSP-P04-W01 decision-record predicate."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "docs/positioning/offers/verify_agentic_delivery_audit_decision.py"
SPEC = importlib.util.spec_from_file_location("verify_agentic_delivery_audit_decision", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AgenticDeliveryAuditDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads(MODULE.RECORD_PATH.read_text(encoding="utf-8"))
        self.offer = MODULE.OFFER_PATH.read_text(encoding="utf-8")

    def run_predicate(self, record: dict, offer: str | None = None) -> tuple[int, str]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        record_path = root / MODULE.RECORD_PATH.name
        offer_path = root / MODULE.OFFER_PATH.name
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        offer_path.write_text(self.offer if offer is None else offer, encoding="utf-8")
        output = io.StringIO()
        with (
            mock.patch.object(MODULE, "RECORD_PATH", record_path),
            mock.patch.object(MODULE, "OFFER_PATH", offer_path),
            redirect_stdout(output),
        ):
            result = MODULE.main()
        return result, output.getvalue()

    def test_canonical_repository_predicate_passes(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = MODULE.main()
        self.assertEqual(0, result, output.getvalue())
        self.assertEqual(f"{MODULE.PASS_LINE}\n", output.getvalue())

    def test_same_length_contract_list_substitution_fails(self) -> None:
        for field in ("exclusions", "success_criteria", "decline_or_pause_when"):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.record)
                changed[field][0] = "arbitrary replacement that removes the contractual boundary"
                result, output = self.run_predicate(changed)
                self.assertEqual(1, result)
                self.assertIn(f"{field} contract differs", output)

    def test_numeric_scalar_and_key_cannot_bypass_price_scan(self) -> None:
        changed = copy.deepcopy(self.record)
        changed["escalation"]["price_exceptions"] = {"USD": 50000}
        result, output = self.run_predicate(changed)
        self.assertEqual(1, result)
        self.assertIn("decision record contract digest differs", output)
        self.assertIn("public pricing leakage: named public currency", output)

    def test_every_canonical_private_source_pattern_fails(self) -> None:
        samples = (
            "/home/alice/private/record.json",
            r"C:\Users\alice\private\record.json",
            "file:///private/record.json",
            ".agent-runtime/codex/worktrees/private",
            "archived_sessions/private.json",
            "123e4567-e89b-42d3-a456-426614174000",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                changed = copy.deepcopy(self.record)
                changed["rollback"] = sample
                result, output = self.run_predicate(changed)
                self.assertEqual(1, result)
                self.assertIn("private-source leakage matched canonical pattern", output)

    def test_generated_offer_drift_from_canonical_source_fails(self) -> None:
        result, output = self.run_predicate(self.record, self.offer + "\nUnchecked hand edit.\n")
        self.assertEqual(1, result)
        self.assertIn("generated offer drifted from the exact canonical commercial-contract render", output)

    def test_scoped_gate_binds_every_owned_input(self) -> None:
        gates = (ROOT / "institutio/governance/gates.yaml").read_text(encoding="utf-8")
        self.assertIn("agentic-delivery-audit-decision-test:", gates)
        for path in (
            "docs/positioning/offers/agentic-delivery-audit.md",
            "docs/positioning/offers/agentic-delivery-audit-decision-record.json",
            "docs/positioning/offers/verify_agentic_delivery_audit_decision.py",
            "institutio/positioning/commercial-contract.yaml",
            "scripts/positioning-offer-artifacts.py",
            "scripts/tests/test_agentic_delivery_audit_decision.py",
        ):
            self.assertIn(path, gates)


if __name__ == "__main__":
    unittest.main()
