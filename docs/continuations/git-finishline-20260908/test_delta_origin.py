#!/usr/bin/env python3
"""Source-delta counterexamples: carried state is not a recovered request."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("delta_origin", Path(__file__).with_name("reconcile-delta-origin.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeltaOriginTest(unittest.TestCase):
    def test_lifecycle_only_changes_remain_observations(self):
        row = {"context": "Existing task", "status": "open"}
        current = {**row, "status": "done"}
        self.assertEqual(module.classify(row, row, current, None), "unchanged_request_fields")

    def test_old_branch_base_does_not_invent_new_requests(self):
        canonical = {"context": "Already in default"}
        self.assertEqual(module.classify(None, None, canonical, canonical), "carried_from_contemporaneous_default")

    def test_staged_request_and_authority_changes_are_not_erased(self):
        base = {"context": "Existing task"}
        staged = {"context": "New request"}
        self.assertEqual(module.classify(base, staged, base, base), "added_or_changed_request")
        scoped = {**base, "execution_requirements": ["different-authority"]}
        self.assertEqual(module.classify(base, base, scoped, base), "added_or_changed_request")

    def test_new_request_without_prior_default_proof_is_retained(self):
        self.assertEqual(module.classify(None, None, {"context": "New"}, None), "added_or_changed_request")

    def test_binding_keeps_candidate_and_does_not_complete_task(self):
        preserve = module.source.opaque("", "recovery-dated-report-observations")
        task = module.source.opaque("task", "T")
        manifest = {
            "atoms": [
                {
                    "atom_id": preserve,
                    "candidate_ids": [preserve],
                    "source_ids": ["stash:0"],
                    "outcome": {"disposition": "unassessed"},
                },
                {
                    "atom_id": task,
                    "candidate_ids": [task],
                    "source_ids": ["stash:1"],
                    "outcome": {"disposition": "unassessed"},
                },
            ],
            "sources": [{"source_id": "stash:0"}, {"source_id": "stash:1"}],
        }
        row = {
            "candidate_id": task,
            "classification": "preserved_projection_observation",
            "canonical_identity_present": True,
            "occurrences": [
                {
                    "classification": "unchanged_request_fields",
                    "request_digests": {"base": "a", "index": "a", "worktree": "a", "prior_default": None},
                }
            ],
        }
        result = module.bind(manifest, {"candidates": [row]}, {})
        self.assertEqual(len(result["atoms"]), 1)
        self.assertEqual(set(result["atoms"][0]["candidate_ids"]), {preserve, task})
        self.assertEqual(result["atoms"][0]["outcome"]["disposition"], "unassessed")
        self.assertEqual(module.bind(result, {"candidates": [row]}, {}), result)
        row["occurrences"][0]["request_digests"]["index"] = "changed"
        with self.assertRaises(ValueError):
            module.bind(manifest, {"candidates": [row]}, {})


if __name__ == "__main__":
    unittest.main()
