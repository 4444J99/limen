#!/usr/bin/env python3
"""Focused unit checks for the PSP-P02-W02 public-safe classifier."""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("estate_classification", ROOT / "scripts/estate-classification.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EstateClassificationTests(unittest.TestCase):
    def test_paginated_objects_slurps_and_flattens_every_page(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout='[[{"login": "example-a"}], [{"login": "example-b"}]]',
            stderr="",
        )
        native_user = mock.Mock(return_value=completed)
        gitvs = SimpleNamespace(_gh_user=native_user)
        with mock.patch.object(MODULE, "load_gitvs", return_value=gitvs):
            self.assertEqual(
                MODULE.paginated_objects("/user/orgs?per_page=100", kind="organization"),
                [{"login": "example-a"}, {"login": "example-b"}],
            )

        native_user.assert_called_once_with(
            ["api", "--paginate", "--slurp", "/user/orgs?per_page=100"],
            timeout=180,
        )

    def test_effective_estate_uses_the_overlay_aware_loader(self) -> None:
        effective = {"repo_overrides": {"opaque-key": {"class": "operation_private"}}}
        load_estate = mock.Mock(return_value=effective)
        gitvs = SimpleNamespace(load_estate=load_estate)
        with mock.patch.object(MODULE, "load_gitvs", return_value=gitvs):
            self.assertIs(MODULE.load_effective_estate(), effective)
        load_estate.assert_called_once_with()

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

        active_cutoff = now - dt.timedelta(days=90)
        maintained_cutoff = now - dt.timedelta(days=365)

        def stamp(value: dt.datetime) -> str:
            return value.isoformat().replace("+00:00", "Z")

        self.assertEqual(MODULE.maturity_for({"pushed_at": stamp(active_cutoff)}, policy, now), "active")
        self.assertEqual(
            MODULE.maturity_for({"pushed_at": stamp(active_cutoff - dt.timedelta(seconds=1))}, policy, now),
            "maintained",
        )
        self.assertEqual(MODULE.maturity_for({"pushed_at": stamp(maintained_cutoff)}, policy, now), "maintained")
        self.assertEqual(
            MODULE.maturity_for({"pushed_at": stamp(maintained_cutoff - dt.timedelta(seconds=1))}, policy, now),
            "dormant",
        )

    def test_maturity_cutoffs_reject_missing_or_non_numeric_schema(self) -> None:
        invalid_policies = [
            {},
            {"maturity": []},
            {"maturity": {"active_within_days": "90", "maintained_within_days": 365}},
            {"maturity": {"active_within_days": 90, "maintained_within_days": False}},
            {"maturity": {"active_within_days": 365, "maintained_within_days": 90}},
        ]
        for policy in invalid_policies:
            with self.subTest(policy=policy):
                with self.assertRaises(MODULE.ClassificationError):
                    MODULE.maturity_cutoffs(policy)

        estate = copy.deepcopy(MODULE.load_yaml(ROOT / "institutio/github/estate.yaml"))
        estate["positioning_estate_classification"]["maturity"] = {
            "values": sorted(MODULE.MATURITY),
            "active_within_days": "private-value-must-not-be-printed",
            "maintained_within_days": 365,
        }
        errors = MODULE.verify_policy(estate)
        self.assertTrue(any("active_within_days" in error for error in errors))
        self.assertNotIn("private-value-must-not-be-printed", " ".join(errors))

    def test_policy_is_complete(self) -> None:
        estate = MODULE.load_yaml(ROOT / "institutio/github/estate.yaml")
        self.assertEqual(MODULE.verify_policy(estate), [])

    def test_unknown_selector_key_fails_closed(self) -> None:
        selector = {"governance_class": "conductor"}
        with self.assertRaisesRegex(MODULE.ClassificationError, "unsupported selector key"):
            MODULE.selector_matches(
                selector,
                governance_class="conductor",
                audience="world",
                product=False,
                row={"private": False, "archived": False},
            )

        estate = copy.deepcopy(MODULE.load_yaml(ROOT / "institutio/github/estate.yaml"))
        estate["positioning_estate_classification"]["primary_order"][0]["when"] = selector
        self.assertTrue(any("unsupported selector key" in error for error in MODULE.verify_policy(estate)))

    def test_repository_identity_digest_rejects_count_preserving_substitution(self) -> None:
        rows = [
            {"full_name": "example/a", "private": False},
            {"full_name": "example/b", "private": True},
        ]
        expected = "3deab778de2b974685ee4cb982b04b8f3d98f5eff2b3ae2d5c06c08e0dca8bdb"
        self.assertEqual(MODULE.repository_identity_digest(rows), expected)
        receipt = {
            "owner_login": "example-owner",
            "owner_user_id": 1,
            "organization_roster": ["example-org"],
            "live_passes": {
                "pass_1_stable_digest": expected,
                "pass_2_stable_digest": expected,
            },
        }
        MODULE.verify_census_identity(
            rows,
            {"login": "example-owner", "id": 1},
            ["example-org"],
            receipt,
        )

        substituted = [rows[0], {"full_name": "example/c", "private": True}]
        with self.assertRaisesRegex(MODULE.ClassificationError, "identity/visibility digest"):
            MODULE.verify_census_identity(
                substituted,
                {"login": "example-owner", "id": 1},
                ["example-org"],
                receipt,
            )

    def test_private_bare_slug_is_guarded_unless_a_public_slug_collides(self) -> None:
        rows = [
            {"full_name": "example-private/sensitive-only", "name": "sensitive-only", "private": True},
            {"full_name": "example-private/shared", "name": "shared", "private": True},
            {"full_name": "example-public/SHARED", "name": "SHARED", "private": False},
        ]
        full_names, bare_slugs = MODULE.private_repository_tokens(rows)
        self.assertEqual(full_names, {"example-private/sensitive-only", "example-private/shared"})
        self.assertEqual(bare_slugs, {"sensitive-only"})

        content = SimpleNamespace(
            returncode=0,
            stdout="+SENSITIVE-ONLY\n+shared\n+descriptive sensitive-only wording\n",
            stderr="",
        )
        added_paths = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[content, added_paths]):
            self.assertEqual(
                MODULE.private_leaks_added("base-ref", full_names, bare_slugs),
                ["sensitive-only"],
            )

    def test_private_name_guard_is_case_insensitive_for_content_and_paths(self) -> None:
        private_name = "private-owner/private-repository"
        content_leak = SimpleNamespace(
            returncode=0,
            stdout="+PRIVATE-OWNER/PRIVATE-REPOSITORY\n",
            stderr="",
        )
        safe_paths = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[content_leak, safe_paths]):
            self.assertEqual(MODULE.private_leaks_added("base-ref", {private_name}), [private_name])

        safe_content = SimpleNamespace(returncode=0, stdout="+public-safe\n", stderr="")
        path_leak = SimpleNamespace(
            returncode=0,
            stdout="docs/PRIVATE-OWNER/PRIVATE-REPOSITORY.md\0",
            stderr="",
        )
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[safe_content, path_leak]):
            self.assertEqual(MODULE.private_leaks_added("base-ref", {private_name}), [private_name])

    def test_private_name_guard_keeps_added_lines_beginning_with_two_pluses(self) -> None:
        private_name = "private-owner/private-repository"
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                "diff --git a/docs/example.md b/docs/example.md\n"
                "--- a/docs/example.md\n"
                "+++ b/docs/example.md\n"
                "@@ -0,0 +1 @@\n"
                "+++ PRIVATE-OWNER/PRIVATE-REPOSITORY\n"
            ),
            stderr="",
        )
        added_paths = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[completed, added_paths]):
            self.assertEqual(MODULE.private_leaks_added("base-ref", {private_name}), [private_name])

    def test_private_internal_disposition_forces_private_only_relevance(self) -> None:
        policy = {"public_relevance": {"products": "product_diligence"}}
        self.assertEqual(MODULE.public_relevance_for("products", "private_internal", policy), "private_only")
        self.assertEqual(MODULE.public_relevance_for("products", "public_evidence", policy), "product_diligence")

    def test_private_name_guard_scans_the_entire_reviewed_diff(self) -> None:
        private_name = "private-owner/private-repository"
        completed = SimpleNamespace(
            returncode=0,
            stdout=f"diff --git a/docs/receipts/example.md b/docs/receipts/example.md\n+{private_name}\n",
            stderr="",
        )
        added_paths = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[completed, added_paths]) as run:
            self.assertEqual(MODULE.private_leaks_added("base-ref", {private_name}), [private_name])

        self.assertEqual(
            run.call_args_list[0].args[0],
            ["git", "diff", "--unified=0", "base-ref...HEAD"],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["git", "diff", "--name-only", "-z", "--diff-filter=A", "--no-renames", "base-ref...HEAD"],
        )

    def test_private_name_guard_does_not_match_a_longer_public_slug(self) -> None:
        private_name = "private-owner/private-repository"
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                "diff --git a/docs/positioning/example.md b/docs/positioning/example.md\n"
                f"+https://github.com/{private_name}-public\n"
            ),
            stderr="",
        )
        added_paths = SimpleNamespace(returncode=0, stdout="docs/positioning/example.md\0", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[completed, added_paths]):
            self.assertEqual(MODULE.private_leaks_added("base-ref", {private_name}), [])

    def test_private_name_guard_scans_added_and_renamed_destinations(self) -> None:
        private_name = "private-owner/private-repository"
        content = SimpleNamespace(
            returncode=0,
            stdout="diff --git a/docs/example.md b/docs/example.md\n+public-safe content\n",
            stderr="",
        )
        added_paths = SimpleNamespace(
            returncode=0,
            stdout=f"docs/{private_name}.md\0",
            stderr="",
        )
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[content, added_paths]):
            self.assertEqual(MODULE.private_leaks_added("base-ref", {private_name}), [private_name])

    def test_private_name_guard_sanitizes_both_diff_timeouts(self) -> None:
        private_value = "private-owner/private-repository"
        first_timeout = MODULE.subprocess.TimeoutExpired(
            cmd=["git", "diff", private_value],
            timeout=60,
            output=private_value,
        )
        with mock.patch.object(MODULE.subprocess, "run", side_effect=first_timeout):
            with self.assertRaises(MODULE.ClassificationError) as raised:
                MODULE.private_leaks_added("base-ref", {private_value})
        self.assertEqual(str(raised.exception), "timed out inspecting reviewed diff")
        self.assertNotIn(private_value, str(raised.exception))

        completed = SimpleNamespace(returncode=0, stdout="+public-safe\n", stderr="")
        second_timeout = MODULE.subprocess.TimeoutExpired(
            cmd=["git", "diff", "--name-only", private_value],
            timeout=60,
            output=private_value,
        )
        with mock.patch.object(MODULE.subprocess, "run", side_effect=[completed, second_timeout]):
            with self.assertRaises(MODULE.ClassificationError) as raised:
                MODULE.private_leaks_added("base-ref", {private_value})
        self.assertEqual(str(raised.exception), "timed out inspecting added paths")
        self.assertNotIn(private_value, str(raised.exception))

    def test_private_classification_failure_does_not_expose_repository_identity(self) -> None:
        private_name = "private-owner/private-repository"
        row = {"full_name": private_name, "private": True, "archived": False, "fork": False}
        estate = {"positioning_estate_classification": {"primary_order": []}, "product_ledger": {"repos": []}}
        gitvs = SimpleNamespace(classify_repo=lambda *_args, **_kwargs: "operation_private")
        with mock.patch.object(MODULE, "load_gitvs", return_value=gitvs):
            with self.assertRaises(MODULE.ClassificationError) as raised:
                MODULE.classify([row], estate, {}, dt.datetime(2026, 8, 10, tzinfo=dt.UTC))
        self.assertNotIn(private_name, str(raised.exception))

    def test_verify_uses_origin_main_and_is_the_strict_gate(self) -> None:
        estate = {
            "positioning_estate_classification": {
                "expected_denominator": {"repositories": 1, "private": 0, "public": 1}
            }
        }
        rows = [{"full_name": "example/public-proof", "private": False}]
        owner = {"login": "example-owner", "id": 1}
        organization_roster = ["example-org"]
        classifications = [{
            "primary_class": "proof",
            "maturity": "active",
            "visibility_disposition": "public_evidence",
            "public_relevance": "primary",
            "governance_class": "proof_public",
            "uncertainty": [],
        }]
        counts = {
            "repository_count": 1,
            "visibility": {"private": 0, "public": 1},
            "uncertainty_queue": {},
        }
        with (
            mock.patch.object(MODULE, "load_effective_estate", return_value=estate),
            mock.patch.object(MODULE, "load_yaml", return_value={}),
            mock.patch.object(MODULE, "load_json", return_value={}) as load_json,
            mock.patch.object(MODULE, "collect_live_estate", return_value=(rows, owner, organization_roster)),
            mock.patch.object(MODULE, "classify", return_value=classifications),
            mock.patch.object(MODULE, "summary", return_value=counts),
            mock.patch.object(MODULE, "verify_policy", return_value=[]) as verify_policy,
            mock.patch.object(MODULE, "verify_census_identity") as identity_guard,
            mock.patch.object(MODULE, "private_leaks_added", return_value=[]) as private_guard,
            mock.patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(MODULE.main([]), 0)
            load_json.assert_not_called()
            verify_policy.assert_not_called()
            identity_guard.assert_not_called()
            private_guard.assert_not_called()

            self.assertEqual(MODULE.main(["--verify"]), 0)
            load_json.assert_called_once_with(MODULE.CENSUS_RECEIPT)
            verify_policy.assert_called_once_with(estate)
            identity_guard.assert_called_once_with(rows, owner, organization_roster, {})
            private_guard.assert_called_once_with("origin/main", set(), set())

    def test_main_sanitizes_unexpected_failures(self) -> None:
        private_value = "private-owner/private-repository"
        stderr = io.StringIO()
        with (
            mock.patch.object(MODULE, "load_effective_estate", side_effect=RuntimeError(private_value)),
            mock.patch("sys.stderr", stderr),
        ):
            self.assertEqual(MODULE.main([]), 1)
        self.assertEqual(
            stderr.getvalue(),
            "estate-classification: FAIL: unexpected classifier failure\n",
        )
        self.assertNotIn(private_value, stderr.getvalue())

    def test_classifier_suite_is_registered_as_a_scoped_gate(self) -> None:
        registry = yaml.safe_load((ROOT / "institutio/governance/gates.yaml").read_text(encoding="utf-8"))
        gate = registry["gates"]["estate-classification-test"]
        self.assertEqual(gate["command"], "python3 scripts/tests/estate-classification.test.py")
        self.assertEqual(
            set(gate["paths"]),
            {
                "scripts/estate-classification.py",
                "scripts/tests/estate-classification.test.py",
                "institutio/github/estate.yaml",
                "institutio/github/access.yaml",
                "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json",
                "scripts/gitvs.py",
            },
        )


if __name__ == "__main__":
    unittest.main()
