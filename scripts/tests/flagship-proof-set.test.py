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

    @staticmethod
    def candidate_from(matrix: dict, candidate_id: str) -> dict:
        return next(row for row in matrix["candidates"] if row["id"] == candidate_id)

    def assert_error_contains(self, matrix: dict, expected: str) -> None:
        errors = MODULE.validate_matrix(matrix, now=self.observed_at, enforce_freshness=True)
        self.assertTrue(any(expected in error for error in errors), errors)

    @staticmethod
    def workflow_payload(workflow: dict) -> dict:
        identity = workflow["workflow_identity"]
        return {
            "status": "completed",
            "conclusion": "success",
            "head_sha": workflow["observed_head"],
            "head_branch": workflow["observed_default_branch"],
            "html_url": workflow["url"],
            "workflow_id": identity["id"],
            "path": identity["path"],
            "name": identity["name"],
        }

    @staticmethod
    def live_snapshot(candidate: dict) -> dict:
        repository = candidate["repository"]
        workflow = next(
            (
                anchor
                for anchor in candidate.get("evidence_anchors", [])
                if anchor.get("kind") == "workflow_run"
            ),
            None,
        )
        default_branch = workflow.get("observed_default_branch") if workflow else "main"
        return {
            "front_door_repositories": [],
            "metadata": {
                repository.casefold(): {
                    "full_name": repository,
                    "private": False,
                    "archived": candidate.get("repository_maturity") == "archived",
                    "default_branch": default_branch,
                }
            },
            "maturity": {repository.casefold(): candidate["repository_maturity"]},
        }

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
        self.assert_error_contains(matrix, "exactly one live workflow_run and one live public_endpoint")

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
        for value in (None, "", "   ", {"statement": "unbounded"}):
            with self.subTest(value=value):
                matrix = copy.deepcopy(self.matrix)
                next(row for row in matrix["candidates"] if row["id"] == "limen")[
                    "flagship_claim"
                ] = value
                self.assert_error_contains(matrix, "complete structured flagship_claim contract")

    def test_selected_claim_contract_rejects_unbounded_or_circular_evidence(self) -> None:
        mutations = (
            ("subject_repository", "example/other", "subject must be the candidate repository"),
            ("excludes", ["adoption"], "must match the required public claim boundary"),
            (
                "evidence_basis",
                ["selection_matrix", "exact_head_workflow", "candidate_bound_public_endpoint"],
                "must match the required public claim boundary",
            ),
            (
                "non_circular_exclusions",
                ["selection_matrix"],
                "must match the required public claim boundary",
            ),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                matrix = copy.deepcopy(self.matrix)
                self.candidate_from(matrix, "limen")["flagship_claim"][field] = value
                self.assert_error_contains(matrix, expected)

        matrix = copy.deepcopy(self.matrix)
        self.candidate_from(matrix, "limen")["flagship_claim"]["statement"] = (
            "Market-leading platform used by millions."
        )
        self.assert_error_contains(matrix, "exceeds the bounded public assertion class")

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

    def test_repository_identity_collisions_are_case_insensitive(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        first, second = matrix["candidates"][:2]
        second["repository"] = first["repository"].upper()
        second["public_url"] = f"https://github.com/{second['repository']}"
        self.assert_error_contains(matrix, "case-insensitive duplicate identities")

    def test_unregistered_repository_identity_is_rejected_without_echoing_it(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        candidate = self.candidate_from(matrix, "limen")
        private_like_identity = "example/internal-only"
        candidate["repository"] = private_like_identity
        candidate["public_url"] = f"https://github.com/{private_like_identity}"
        candidate["flagship_claim"]["subject_repository"] = private_like_identity
        errors = MODULE.validate_matrix(matrix, now=self.observed_at, enforce_freshness=True)
        self.assertTrue(any("not present in the tracked public census" in error for error in errors), errors)
        self.assertFalse(any(private_like_identity in error for error in errors), errors)

    def test_authoritative_w02_projection_cannot_omit_a_tagged_row(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        candidate = self.candidate_from(matrix, "hokage_chess")
        candidate["source_sets"] = ["current_profile"]
        self.assert_error_contains(matrix, "matrix W02 rows do not match the authoritative source projection")

    def test_authoritative_w02_projection_rejects_a_unique_public_substitution(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        candidate_repositories = {
            row.get("repository") for row in matrix["candidates"] if row.get("repository")
        }
        public_repositories, _, _ = MODULE.load_public_census_contract()
        substitute = next(
            repository
            for repository in sorted(public_repositories)
            if repository not in candidate_repositories
        )
        candidate = self.candidate_from(matrix, "hokage_chess")
        candidate["repository"] = substitute
        candidate["public_url"] = f"https://github.com/{substitute}"
        self.assert_error_contains(matrix, "matrix W02 rows do not match the authoritative source projection")

    def test_repository_public_url_must_be_canonical(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        self.candidate_from(matrix, "limen")["public_url"] = "https://github.com/organvm/limen/"
        self.assert_error_contains(matrix, "canonical public GitHub repository URL")

    def test_selected_anchor_kinds_are_both_required(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        candidate = self.candidate_from(matrix, "limen")
        candidate["evidence_anchors"] = [candidate["evidence_anchors"][0]]
        self.assert_error_contains(matrix, "exactly one live workflow_run and one live public_endpoint")

    def test_workflow_display_url_and_identity_are_structurally_bound(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        workflow = self.candidate_from(matrix, "limen")["evidence_anchors"][0]
        workflow["url"] = "https://github.com/organvm/limen/actions/runs/1"
        self.assert_error_contains(matrix, "workflow display URL must match its repository-bound run")
        matrix = copy.deepcopy(self.matrix)
        self.candidate_from(matrix, "limen")["evidence_anchors"][0]["workflow_identity"] = {
            "id": 1,
            "name": "CI",
        }
        self.assert_error_contains(matrix, "workflow identity must pin id, path, and name")

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
        candidate = copy.deepcopy(self.candidate("public_records"))
        repository = candidate["repository"]
        workflow = next(anchor for anchor in candidate["evidence_anchors"] if anchor["kind"] == "workflow_run")
        observed_head = workflow["observed_head"]
        advanced_head = "f" * 40

        def fake_command(args: list[str]) -> dict:
            path = args[-1]
            if path == f"repos/{repository}/commits/main":
                return {"sha": advanced_head}
            if path == workflow["github_api_path"]:
                return self.workflow_payload(workflow)
            self.fail(f"unexpected live query: {path}")

        with (
            mock.patch.object(MODULE, "live_w02_snapshot", return_value=self.live_snapshot(candidate)),
            mock.patch.object(MODULE, "command_json", side_effect=fake_command),
            mock.patch.object(MODULE, "http_status", return_value=200),
        ):
            errors = MODULE.validate_live({"candidates": [candidate]})
        self.assertTrue(any("current default-branch head" in error for error in errors), errors)

    def test_same_repository_dated_snapshot_survives_current_main_advance(self) -> None:
        candidate = copy.deepcopy(self.candidate("limen"))
        workflow = next(anchor for anchor in candidate["evidence_anchors"] if anchor["kind"] == "workflow_run")

        def fake_command(args: list[str]) -> dict:
            path = args[-1]
            if path == workflow["github_api_path"]:
                return self.workflow_payload(workflow)
            self.fail(f"dated snapshot must not query a moving current head: {path}")

        with (
            mock.patch.object(MODULE, "live_w02_snapshot", return_value=self.live_snapshot(candidate)),
            mock.patch.object(MODULE, "command_json", side_effect=fake_command),
            mock.patch.object(MODULE, "http_status", return_value=200),
        ):
            self.assertEqual(MODULE.validate_live({"candidates": [candidate]}), [])

    def test_live_workflow_identity_is_pinned(self) -> None:
        candidate = copy.deepcopy(self.candidate("public_records"))
        workflow = next(anchor for anchor in candidate["evidence_anchors"] if anchor["kind"] == "workflow_run")

        def fake_command(args: list[str]) -> dict:
            path = args[-1]
            if path == workflow["github_api_path"]:
                payload = self.workflow_payload(workflow)
                payload["workflow_id"] += 1
                return payload
            if path.endswith("/commits/main"):
                return {"sha": workflow["observed_head"]}
            self.fail(f"unexpected live query: {path}")

        with (
            mock.patch.object(MODULE, "live_w02_snapshot", return_value=self.live_snapshot(candidate)),
            mock.patch.object(MODULE, "command_json", side_effect=fake_command),
            mock.patch.object(MODULE, "http_status", return_value=200),
        ):
            errors = MODULE.validate_live({"candidates": [candidate]})
        self.assertTrue(any("workflow identity differs" in error for error in errors), errors)

    def test_live_repository_maturity_comes_from_w02_metadata(self) -> None:
        candidate = copy.deepcopy(self.candidate("universal_mail"))
        snapshot = self.live_snapshot(candidate)
        snapshot["maturity"][candidate["repository"].casefold()] = "maintained"
        with mock.patch.object(MODULE, "live_w02_snapshot", return_value=snapshot):
            errors = MODULE.validate_live({"candidates": [candidate]})
        self.assertTrue(any("maturity differs from current W02 metadata" in error for error in errors), errors)

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
        self.assertEqual(
            MODULE.repository_workflow_api_path(
                "repos/OrganVM/Limen/actions/runs/1", "organvm/limen"
            ),
            "repos/OrganVM/Limen/actions/runs/1",
        )
        self.assertIsNone(
            MODULE.repository_workflow_api_path(
                "repos/example/other/actions/runs/1", "organvm/limen"
            )
        )


if __name__ == "__main__":
    unittest.main()
