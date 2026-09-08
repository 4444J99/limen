#!/usr/bin/env python3
"""Counterexamples for source-lineage reconciliation, separate from delivery."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("reconcile_sources", Path(__file__).with_name("reconcile-sources.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReconcileTest(unittest.TestCase):
    def test_current_done_is_not_delivery(self):
        task = {"id": "T", "title": "Retain an intent", "status": "done"}
        candidate = {"id": "T", "source_indices": [0], "source_delta_types": ["new_task"]}
        result = module.task_assessment(candidate, [(0, task)], {"T": task})
        self.assertEqual(result["lineage_assessment"], "exact_source_intent_retained")
        self.assertEqual(result["delivery_assessment"], "unverified")

    def test_a_matching_snapshot_cannot_erase_another_request(self):
        old = {"id": "T", "context": "Original request"}
        new = {"id": "T", "context": "Changed request"}
        candidate = {"id": "T", "source_indices": [0, 1], "source_delta_types": ["content_change"]}
        result = module.task_assessment(candidate, [(0, old), (1, new)], {"T": new})
        self.assertEqual(result["lineage_assessment"], "source_variant_retained_other_variants_differ")
        self.assertEqual(result["source_comparisons"][0]["different_intent_fields"], ["context"])

    def test_missing_recovery_variant_does_not_deliver_original(self):
        candidate = {
            "id": "RECOVER-T",
            "source_indices": [0],
            "source_delta_types": ["new_task"],
            "original_id_candidate": "T",
        }
        result = module.task_assessment(candidate, [(0, {"id": "RECOVER-T"})], {"T": {"status": "done"}})
        self.assertEqual(result["lineage_assessment"], "original_identity_present")
        self.assertEqual(result["delivery_assessment"], "unverified")

    def test_review_replies_keep_their_frozen_identity(self):
        frozen = [
            {
                "id": i,
                "html_url": f"https://github.com/o/r/pull/1#discussion_r{i}",
                "body": f"body {i}",
                "path": "code.py",
                "source_pr": 1,
            }
            for i in [1, 2, 3]
        ]
        native = [dict(r) for r in frozen]
        native[1]["in_reply_to_id"] = 1
        native[2]["in_reply_to_id"] = 2
        result = module.review_lineage(frozen, native)
        self.assertEqual([r["root_review_id"] for r in result], ["1", "1", "1"])
        self.assertEqual([r["record_kind"] for r in result], ["root_finding", "reply", "reply"])

    def test_missing_changed_cyclic_or_duplicate_reviews_fail(self):
        frozen = [
            {
                "id": 1,
                "html_url": "https://github.com/o/r/pull/1#discussion_r1",
                "body": "frozen",
                "path": "code.py",
                "source_pr": 1,
            }
        ]
        for native in [
            [],
            [{**frozen[0], "body": "edited"}],
            [{**frozen[0], "in_reply_to_id": 9}],
            [{**frozen[0], "in_reply_to_id": 1}],
            [dict(frozen[0]), dict(frozen[0])],
        ]:
            with self.subTest(native=native), self.assertRaises(ValueError):
                module.review_lineage(frozen, native)

    def test_reply_binding_preserves_candidates_and_is_idempotent(self):
        root, reply = module.opaque("review", "1"), module.opaque("review", "2")
        manifest = {
            "atoms": [
                {"atom_id": root, "candidate_ids": [root], "source_ids": ["branch:0"]},
                {"atom_id": reply, "candidate_ids": [reply], "source_ids": ["pr:0"]},
            ],
            "sources": [{"source_id": "branch:0"}, {"source_id": "pr:0"}],
        }
        rows = [
            {"review_id": "1", "root_review_id": "1", "record_kind": "root_finding"},
            {"review_id": "2", "root_review_id": "1", "record_kind": "reply", "source_body_sha256": "abc"},
        ]
        rec = {"reviews": rows, "tasks": []}
        decisions = {
            "replies": [
                {
                    "review_id": "2",
                    "root_review_id": "1",
                    "source_body_sha256": "abc",
                    "disposition": "same_finding_evidence",
                }
            ]
        }
        result = module.bind_manifest(manifest, rec, decisions, {})
        self.assertEqual(len(result["atoms"]), 1)
        self.assertEqual(set(result["atoms"][0]["candidate_ids"]), {root, reply})
        self.assertEqual(result, module.bind_manifest(result, rec, decisions, {}))
        with self.assertRaises(ValueError):
            module.bind_manifest(manifest, rec, {"replies": []}, {})


if __name__ == "__main__":
    unittest.main()
