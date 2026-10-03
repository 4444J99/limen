#!/usr/bin/env python3
"""Focused capacity tests; no credentials, network, or custody mutations."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "horrevm", Path(__file__).resolve().parents[1] / "horrevm-custody.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.budgets = MODULE.BUDGET_GB.copy()
        MODULE.BUDGET_GB.update(gdrive=None, dropbox=1)

    def tearDown(self):
        MODULE.BUDGET_GB.update(self.budgets)

    def test_drive_admits_existing_capacity_above_old_cap(self):
        self.assertTrue(MODULE.transfer_envelope("gdrive", 19_000_000_000, 40_000_000_000)["admitted"])

    def test_unknown_or_invalid_quota_fails_closed(self):
        for free in (None, True, "100", -1, float("inf"), float("nan")):
            with self.subTest(free=free):
                self.assertFalse(MODULE.transfer_envelope("gdrive", 1, free)["admitted"])

    def test_generation_reserve(self):
        self.assertFalse(MODULE.transfer_envelope("gdrive", 10, 19)["admitted"])
        self.assertTrue(MODULE.transfer_envelope("gdrive", 10, 20)["admitted"])

    def test_explicit_budget_preserved(self):
        MODULE.BUDGET_GB["gdrive"] = 5
        self.assertEqual(MODULE.transfer_envelope("gdrive", 6_000_000_000, 100_000_000_000)["reason"], "operator-budget-exceeded")

    def test_dropbox_is_not_bulk_fallback(self):
        self.assertFalse(MODULE.transfer_envelope("dropbox", 2_000_000_000, 100_000_000_000)["admitted"])


if __name__ == "__main__":
    unittest.main()
