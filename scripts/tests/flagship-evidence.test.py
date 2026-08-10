#!/usr/bin/env python3
"""Focused regression checks for PSP-P02-W04/W05 flagship evidence."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("flagship_evidence", ROOT / "scripts/flagship-evidence.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FlagshipEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = MODULE.load_yaml(MODULE.INDEX)

    def assert_error_contains(self, index: dict, expected: str) -> None:
        errors = MODULE.validate_index(index)
        self.assertTrue(any(expected in error for error in errors), errors)

    def test_canonical_index_is_valid(self) -> None:
        self.assertEqual(MODULE.validate_index(self.index), [])

    def test_requires_exactly_the_selected_w03_set(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["id"] = "unapproved_flagship"
        self.assert_error_contains(index, "packet ids must be")

    def test_rejects_private_addendum_without_custody(self) -> None:
        index = copy.deepcopy(self.index)
        index["privacy"]["encrypted_addendum"]["status"] = "invented"
        self.assert_error_contains(index, "encrypted addendum")

    def test_rejects_a_formal_completion_rewrite(self) -> None:
        index = copy.deepcopy(self.index)
        index["dependency_gate"]["w04_state"] = "closed"
        self.assert_error_contains(index, "formally open")

    def test_rejects_nonexact_metric_comparison(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["metrics"][0]["comparison"] = "approximate"
        self.assert_error_contains(index, "exact, dated comparison")


if __name__ == "__main__":
    unittest.main()
