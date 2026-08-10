#!/usr/bin/env python3
"""Focused unit checks for the PSP-P02-W02 public-safe classifier."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("estate_classification", ROOT / "scripts/estate-classification.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EstateClassificationTests(unittest.TestCase):
    def test_partner_precedes_private_and_product(self) -> None:
        row = {"private": True, "archived": False}
        self.assertTrue(MODULE.selector_matches({"audience": "collab"}, governance_class="operation_private", audience="collab", product=True, row=row))
        self.assertTrue(MODULE.selector_matches({"visibility": "private"}, governance_class="operation_private", audience="collab", product=True, row=row))

    def test_maturity_boundaries(self) -> None:
        policy = {"maturity": {"active_within_days": 90, "maintained_within_days": 365}}
        now = dt.datetime(2026, 8, 10, tzinfo=dt.UTC)
        self.assertEqual(MODULE.maturity_for({"pushed_at": "2026-08-01T00:00:00Z"}, policy, now), "active")
        self.assertEqual(MODULE.maturity_for({"pushed_at": "2026-02-01T00:00:00Z"}, policy, now), "maintained")
        self.assertEqual(MODULE.maturity_for({"pushed_at": "2024-01-01T00:00:00Z"}, policy, now), "dormant")
        self.assertEqual(MODULE.maturity_for({"archived": True}, policy, now), "archived")

    def test_policy_is_complete(self) -> None:
        estate = MODULE.load_yaml(ROOT / "institutio/github/estate.yaml")
        self.assertEqual(MODULE.verify_policy(estate), [])


if __name__ == "__main__":
    unittest.main()
