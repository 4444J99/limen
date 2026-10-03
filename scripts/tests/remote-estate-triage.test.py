#!/usr/bin/env python3
"""Adversarial checks for triage coverage, authority, and review holds."""

import copy
import runpy
import unittest
from pathlib import Path

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "remote-estate-triage.py"))


class TriageTests(unittest.TestCase):
    def snapshot(self):
        owner = "https://github.com/4444J99/limen/issues/2614"
        return {
            "schema": MODULE["SCHEMA"], "repository": "4444J99/limen",
            "repository_id": 1255213941,
            "counts": {"issues": 1, "prs": 1, "branches": 1},
            "issues": [{"number": 1, "owner_url": owner, "category": "review", "completion_proven": False}],
            "prs": [{"number": 2, "owner_url": owner, "category": "review", "verification_proven_by_this_audit": False}],
            "branches": [{"name": "fix/example", "owner_url": owner, "category": "review", "deletion_eligible": False}],
        }

    def test_duplicate_cannot_hide_missing_item(self):
        s = self.snapshot()
        s["issues"] *= 2
        s["counts"]["issues"] = 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE["check"](s)

    def test_routing_cannot_claim_terminal_authority(self):
        for kind, field in [("issues", "completion_proven"), ("prs", "verification_proven_by_this_audit"), ("branches", "deletion_eligible")]:
            s = self.snapshot()
            s[kind][0][field] = True
            with self.assertRaises(ValueError):
                MODULE["check"](s)

    def test_private_payload_and_foreign_owner_rejected(self):
        for field, value in [("body", "private source"), ("local_path", "/private/source"), ("owner_url", "https://github.com/other/repo/issues/1")]:
            s = copy.deepcopy(self.snapshot())
            s["issues"][0][field] = value
            with self.assertRaises(ValueError):
                MODULE["check"](s)

    def test_historical_merge_never_grants_retirement(self):
        fn = MODULE["branch_category"]
        self.assertEqual(fn("fix/old", protected=False, local=False, open_pr=None, ancestor=False, historical_pr=9), "historical-pr-successor-review")
        self.assertEqual(fn("preserve/original", protected=False, local=False, open_pr=None, ancestor=True, historical_pr=9), "intentional-preservation")
        self.assertEqual(fn("fix/live", protected=False, local=True, open_pr=8, ancestor=True, historical_pr=9), "local-worktree-owner-review")

    def test_gated_label_is_observation_not_completion(self):
        category, _ = MODULE["issue_category"](99, ["needs-human"])
        self.assertEqual(category, "human-gate-owner-recheck")
        MODULE["check"](self.snapshot())

    def test_explicit_hold_survives_other_readiness_signals(self):
        category = MODULE["pr_category"](2777, [], "", dirty=False, empty=False)
        self.assertEqual(category, "explicit-review-hold")


if __name__ == "__main__":
    unittest.main()
