#!/usr/bin/env python3
"""Focused regression checks for the PSP-P02-W03 flagship matrix."""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("flagship_proof_set", ROOT / "scripts/flagship-proof-set.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FlagshipProofSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = MODULE.load_matrix()
        self.observed_at = dt.datetime(2026, 8, 10, 16, 57, 12, tzinfo=dt.UTC)

    def candidate(self, candidate_id: str) -> dict:
        return next(row for row in self.matrix["candidates"] if row["id"] == candidate_id)

    def assert_error_contains(self, matrix: dict, expected: str) -> None:
        errors = MODULE.validate_matrix(matrix, now=self.observed_at, enforce_freshness=True)
        self.assertTrue(any(expected in error for error in errors), errors)

    def test_canonical_matrix_is_valid(self) -> None:
        self.assertEqual(
            MODULE.validate_matrix(self.matrix, now=self.observed_at, enforce_freshness=True),
            [],
        )

    def test_duplicate_selected_story_role_is_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        selected = [row for row in matrix["candidates"] if row["status"] == "selected"]
        selected[1]["story_role"] = selected[0]["story_role"]
        self.assert_error_contains(matrix, "duplicate selected story roles")

    def test_missing_live_evidence_anchor_is_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        next(row for row in matrix["candidates"] if row["id"] == "limen")["evidence_anchors"] = []
        self.assert_error_contains(matrix, "missing a live evidence anchor")

    def test_private_only_dependency_is_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        next(row for row in matrix["candidates"] if row["id"] == "public_records")["private_only_dependencies"] = [
            "private implementation"
        ]
        self.assert_error_contains(matrix, "private-only dependency")

    def test_stale_selected_candidate_is_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        next(row for row in matrix["candidates"] if row["id"] == "ai_chat_exporter")["stale"] = True
        self.assert_error_contains(matrix, "selected candidate is stale")

    def test_excluded_selected_candidate_is_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        next(row for row in matrix["candidates"] if row["id"] == "limen")["eligible"] = False
        self.assert_error_contains(matrix, "marked excluded/ineligible")

    def test_weighted_total_drift_is_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        next(row for row in matrix["candidates"] if row["id"] == "public_records")["weighted_total"] = 100
        self.assert_error_contains(matrix, "does not equal")


if __name__ == "__main__":
    unittest.main()
