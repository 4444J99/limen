#!/usr/bin/env python3
"""Focused regression checks for the PSP-P02-W03 flagship matrix."""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


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

    def test_boolean_numeric_contract_values_are_rejected(self) -> None:
        mutations = (
            (("rubric", "dimensions", "technical_depth", "weight"), True, "integer weight"),
            (("selection_policy", "minimum_selected"), True, "integer selected bounds"),
            (
                ("selection_policy", "minimum_dimension_scores", "public_visibility"),
                False,
                "public_visibility is below the selected minimum",
            ),
        )
        for path, value, expected in mutations:
            with self.subTest(path=path):
                matrix = copy.deepcopy(self.matrix)
                target = matrix
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.assert_error_contains(matrix, expected)

        matrix = copy.deepcopy(self.matrix)
        next(row for row in matrix["candidates"] if row["id"] == "limen")["evidence_anchors"][0][
            "max_age_days"
        ] = True
        self.assert_error_contains(matrix, "valid observation and max age")

    def test_dimension_minima_must_be_a_mapping(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["selection_policy"]["minimum_dimension_scores"] = ["public_visibility"]
        self.assert_error_contains(matrix, "minimum_dimension_scores must be a nonempty mapping")

    def test_selected_candidate_requires_a_bounded_claim(self) -> None:
        for value in (None, "", "   "):
            with self.subTest(value=value):
                matrix = copy.deepcopy(self.matrix)
                next(row for row in matrix["candidates"] if row["id"] == "limen")[
                    "flagship_claim"
                ] = value
                self.assert_error_contains(matrix, "nonempty flagship_claim")

    def test_duplicate_repository_and_endpoint_identities_are_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        first, second = matrix["candidates"][:2]
        second["repository"] = first["repository"]
        first_endpoint = next(
            anchor for anchor in first["evidence_anchors"] if anchor["kind"] == "public_endpoint"
        )
        second_endpoint = next(
            anchor for anchor in second["evidence_anchors"] if anchor["kind"] == "public_endpoint"
        )
        second_endpoint["deployment_identity"] = first_endpoint["deployment_identity"]
        second_endpoint["url"] = first_endpoint["url"]
        self.assert_error_contains(matrix, "duplicate candidate repositories")
        self.assert_error_contains(matrix, "duplicate endpoint identities")
        self.assert_error_contains(matrix, "duplicate endpoint URLs")

    def test_endpoint_anchor_cannot_be_swapped_between_selected_candidates(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        records = next(row for row in matrix["candidates"] if row["id"] == "public_records")
        exporter = next(row for row in matrix["candidates"] if row["id"] == "ai_chat_exporter")
        records_endpoint = next(
            anchor for anchor in records["evidence_anchors"] if anchor["kind"] == "public_endpoint"
        )
        exporter_endpoint = next(
            anchor for anchor in exporter["evidence_anchors"] if anchor["kind"] == "public_endpoint"
        )
        records_endpoint["url"] = exporter_endpoint["url"]
        self.assert_error_contains(matrix, "endpoint identity is not bound to this candidate")

    def test_live_workflow_must_match_current_default_branch_head(self) -> None:
        candidate = copy.deepcopy(self.candidate("limen"))
        observed_head = next(
            anchor["observed_head"]
            for anchor in candidate["evidence_anchors"]
            if anchor["kind"] == "workflow_run"
        )
        advanced_head = "f" * 40

        def fake_command(args: list[str]) -> dict:
            path = args[-1]
            if path == "repos/organvm/limen":
                return {"private": False, "archived": False, "default_branch": "main"}
            if path == "repos/organvm/limen/commits/main":
                return {"sha": advanced_head}
            if path.startswith("repos/organvm/limen/actions/runs/"):
                return {"status": "completed", "conclusion": "success", "head_sha": observed_head}
            self.fail(f"unexpected live query: {path}")

        with (
            mock.patch.object(MODULE, "command_json", side_effect=fake_command),
            mock.patch.object(MODULE, "http_status", return_value=200),
        ):
            errors = MODULE.validate_live({"candidates": [candidate]})
        self.assertTrue(any("current default-branch head" in error for error in errors), errors)

    def test_live_anchor_rejects_credentials_and_private_ip_hosts(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        candidate = next(row for row in matrix["candidates"] if row["id"] == "limen")
        candidate["evidence_anchors"][1]["url"] = "https://token@127.0.0.1/private"
        self.assert_error_contains(matrix, "credential-free public HTTPS hostname")

    def test_live_endpoint_fetch_is_restricted_to_selected_public_hosts(self) -> None:
        with self.assertRaises(MODULE.ProofSetError, msg="untrusted live endpoint must fail before curl"):
            MODULE.validate_live_endpoint_url("https://example.test/not-an-approved-anchor")

    def test_workflow_api_path_is_bound_to_the_candidate_repository(self) -> None:
        self.assertIsNone(MODULE.repository_workflow_api_path("--method=DELETE", "organvm/limen"))
        self.assertIsNone(
            MODULE.repository_workflow_api_path(
                "repos/example/other/actions/runs/1", "organvm/limen"
            )
        )


if __name__ == "__main__":
    unittest.main()
