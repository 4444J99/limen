#!/usr/bin/env python3
"""Focused regression checks for PSP-P02-W04/W05 flagship evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
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

    def test_rejects_repository_substitution_for_selected_flagship(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["public_repository"] = "example/replacement"
        self.assert_error_contains(index, "W03-selected public repository")

    def test_rejects_duplicate_source_kinds(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["sources"][1] = copy.deepcopy(index["packets"][0]["sources"][0])
        self.assert_error_contains(index, "exactly one workflow and public endpoint")

    def test_rejects_packet_path_traversal(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["path"] = "../README.md"
        self.assert_error_contains(index, "packet path must exist")

    def test_rejects_invalid_dependency_state(self) -> None:
        index = copy.deepcopy(self.index)
        index["dependency_gate"]["w04_state"] = "complete"
        self.assert_error_contains(index, "dependency state must be open or closed")

    def test_rejects_out_of_order_dependency_closure(self) -> None:
        index = copy.deepcopy(self.index)
        index["dependency_gate"]["w04_state"] = "closed"
        self.assert_error_contains(index, "W04 may close only after W03")

    def test_live_dependency_state_must_match_issue_owner(self) -> None:
        responses = {
            "2175": "closed",
            "2176": "open",
            "2177": "open",
        }

        def fetcher(url: str) -> tuple[int, bytes]:
            issue_number = url.rsplit("/", 1)[-1]
            return 200, json.dumps({"state": responses[issue_number]}).encode("utf-8")

        errors = MODULE.verify_dependency_states(self.index, fetcher)
        self.assertTrue(any("w03" in error and "live issue state" in error for error in errors), errors)

    def test_rejects_nonexact_metric_comparison(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["metrics"][0]["comparison"] = "approximate"
        self.assert_error_contains(index, "exact, dated comparison")

    def test_json_observation_must_read_the_declared_packet_endpoint(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["metrics"][0]["source_url"] = "https://api.github.com/repos/organvm/limen"
        self.assert_error_contains(index, "JSON observation source must equal the packet public endpoint")

    def test_rejects_nonnumeric_observed_metric(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["metrics"][0]["observed_value"] = "many"
        self.assert_error_contains(index, "observed metric values must be numeric")

    def test_rejects_incomplete_w08_claim_import(self) -> None:
        index = copy.deepcopy(self.index)
        index["w08_research_import"]["claims"].pop()
        self.assert_error_contains(index, "classify each ratified claim exactly once")

    def test_rejects_w08_wording_drift_from_immutable_source(self) -> None:
        index = copy.deepcopy(self.index)
        index["w08_research_import"]["claims"][0]["public_wording"] = "Replacement wording"
        self.assert_error_contains(index, "wording and receipt sets must match")

    def test_rejects_w08_receipt_drift_from_immutable_source(self) -> None:
        index = copy.deepcopy(self.index)
        index["w08_research_import"]["claims"][0]["required_receipts"] = ["replacement"]
        self.assert_error_contains(index, "wording and receipt sets must match")

    def test_rejects_w08_source_artifact_digest_drift(self) -> None:
        index = copy.deepcopy(self.index)
        index["w08_research_import"]["source_sha256"] = "0" * 64
        self.assert_error_contains(index, "immutable source artifact SHA-256")

    def test_rejects_collapsed_w08_adjudication_layers(self) -> None:
        index = copy.deepcopy(self.index)
        del index["w08_research_import"]["claims"][0]["layers"]["implication"]
        self.assert_error_contains(index, "preserve all four adjudication layers")

    def test_rejects_claims_ledger_projection_drift(self) -> None:
        ledger = MODULE.CLAIMS_LEDGER.read_text(encoding="utf-8")
        drifted = ledger.replace("`profile-zero-manual-upkeep`", "`missing-claim`", 1)
        errors = MODULE.validate_w08_import(self.index, drifted)
        self.assertTrue(any("profile-zero-manual-upkeep" in error for error in errors), errors)

    def test_rejects_credentialed_or_private_network_sources(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["sources"][1]["url"] = "https://token@127.0.0.1/private"
        self.assert_error_contains(index, "credential-free selected public host")

    def test_fetch_rejects_unselected_hosts_before_network_access(self) -> None:
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.fetch("https://example.test/untrusted")

    def test_gate_covers_every_consumed_evidence_input(self) -> None:
        registry = MODULE.load_yaml(ROOT / "institutio/governance/gates.yaml")
        paths = registry["gates"]["flagship-evidence-test"]["paths"]
        self.assertIn("docs/positioning/evidence/**", paths)
        self.assertIn("docs/positioning/claims-ledger.md", paths)
        self.assertIn("docs/positioning/flagship-proof-set.yaml", paths)

    def test_term_metric_derives_exact_count_instead_of_presence_only(self) -> None:
        metric = self.index["packets"][1]["metrics"][0]
        paths = ["california", "texas", "florida", "newyork", "illinois"]
        payload = json.dumps(
            {
                "truncated": False,
                "tree": [
                    {"type": "blob", "path": f"scripts/scrapers/states/{name}.ts"}
                    for name in paths
                ],
            }
        ).encode("utf-8")
        errors = MODULE.exact_count_errors("public_records", metric, payload)
        self.assertTrue(any("derived 5, expected 4" in error for error in errors), errors)

    def test_term_metric_rejects_truncated_count_source(self) -> None:
        metric = self.index["packets"][1]["metrics"][0]
        payload = json.dumps({"truncated": True, "tree": []}).encode("utf-8")
        errors = MODULE.exact_count_errors("public_records", metric, payload)
        self.assertTrue(any("truncated" in error for error in errors), errors)

    def test_rejects_term_metric_without_count_observation(self) -> None:
        index = copy.deepcopy(self.index)
        del index["packets"][1]["metrics"][0]["count_observation"]
        self.assert_error_contains(index, "term-based metric must declare an exact count observation")

    def test_rejects_count_source_not_pinned_to_repository_and_workflow_head(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][1]["metrics"][0]["count_observation"]["api_url"] = (
            "https://api.github.com/repos/organvm/limen/git/trees/"
            "139fa7b40d875ecfe3a8c693dedfab46671739fd?recursive=1"
        )
        self.assert_error_contains(index, "count source must bind public_repository and workflow head")

    def test_packet_markdown_must_match_machine_index(self) -> None:
        packet = self.index["packets"][0]
        packet_text = (ROOT / packet["path"]).read_text(encoding="utf-8")
        drifted = packet_text.replace(packet["metrics"][0]["public_safe_claim"], "Unsupported replacement.")
        errors = MODULE.validate_packet_markdown(packet, drifted)
        self.assertTrue(any("public_tasks_total claim" in error for error in errors), errors)

    def test_workflow_urls_must_bind_the_selected_repository(self) -> None:
        index = copy.deepcopy(self.index)
        index["packets"][0]["sources"][0]["api_url"] = (
            "https://api.github.com/repos/organvm-iii-ergon/a-i-chat--exporter/actions/runs/31404705695"
        )
        self.assert_error_contains(index, "workflow API and human URLs must bind")

    def test_live_workflow_response_must_match_repository_and_human_url(self) -> None:
        packet = self.index["packets"][0]
        source = packet["sources"][0]
        run = {
            "repository": {"full_name": "organvm-iii-ergon/a-i-chat--exporter"},
            "html_url": "https://github.com/organvm/limen/actions/runs/1",
            "url": source["api_url"],
        }
        errors = MODULE.validate_workflow_run_response(packet, source, run)
        self.assertTrue(any("repository" in error for error in errors), errors)
        self.assertTrue(any("html_url" in error for error in errors), errors)

    def test_static_validation_requires_all_live_source_fields(self) -> None:
        index = copy.deepcopy(self.index)
        del index["packets"][0]["sources"][0]["expected_conclusion"]
        del index["packets"][0]["sources"][0]["observed_head"]
        del index["packets"][0]["sources"][1]["expected_http_status"]
        errors = MODULE.verify_evidence(index, live=True)
        self.assertTrue(any("expected_conclusion" in error for error in errors), errors)
        self.assertTrue(any("observed_head" in error for error in errors), errors)
        self.assertTrue(any("expected_http_status" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
