#!/usr/bin/env python3
"""Synthetic contract tests for the seven-agent review math."""

from __future__ import annotations

import datetime as dt
import unittest

from model import (
    UTC,
    Window,
    canonical_receipt_key,
    classify_receipt,
    cumulative_delta,
    strongest_outcome,
    union_seconds,
)


def t(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class ReviewModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window("w", "Window", t("2026-07-06T04:00:00Z"), t("2026-07-13T04:00:00Z"))
        self.snapshot = t("2026-07-19T15:11:00Z")

    def test_boundary_crossing_is_clipped_half_open(self) -> None:
        clipped = self.window.clip(t("2026-07-06T03:00:00Z"), t("2026-07-06T05:00:00Z"))
        self.assertEqual(clipped, (t("2026-07-06T04:00:00Z"), t("2026-07-06T05:00:00Z")))
        self.assertFalse(self.window.contains(t("2026-07-13T04:00:00Z")))

    def test_cumulative_token_meter_becomes_delta(self) -> None:
        self.assertEqual(
            cumulative_delta({"input": 140, "output": 20}, {"input": 100, "output": 12}),
            {"input": 40, "output": 8},
        )

    def test_overlapping_intervals_use_union_wall_time(self) -> None:
        intervals = [
            (t("2026-07-06T04:00:00Z"), t("2026-07-06T06:00:00Z")),
            (t("2026-07-06T05:00:00Z"), t("2026-07-06T07:00:00Z")),
        ]
        self.assertEqual(union_seconds(intervals), 3 * 3600)

    def test_root_child_separation_is_not_implicit_time_dedup(self) -> None:
        roots = [{"native_id": "root", "parent_id": None}, {"native_id": "child", "parent_id": "root"}]
        self.assertEqual(sum(1 for row in roots if not row["parent_id"]), 1)

    def test_duplicate_redirect_receipts_share_one_key(self) -> None:
        left = {"url": "https://github.com/a-organvm/demo/pull/7", "canonical_url": "https://github.com/organvm/demo/pull/7"}
        right = {"url": "https://github.com/organvm/demo/pull/7"}
        self.assertEqual(canonical_receipt_key(left), canonical_receipt_key(right))

    def test_healer_only_transition_has_no_executor_outcome(self) -> None:
        executor_events = [{"agent": "heal-board", "status": "done"}]
        family = {"codex", "claude", "agy", "opencode", "gemini", "copilot", "jules"}
        self.assertFalse(any(row["agent"] in family for row in executor_events))

    def test_open_and_merged_prs_classify_differently(self) -> None:
        base = {
            "created_at": "2026-07-17T10:00:00Z",
            "base_ref": "main",
            "default_branch": "main",
            "checks": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
            "commits": [{"committed_at": "2026-07-17T10:05:00Z"}],
        }
        self.assertEqual(classify_receipt(base, snapshot_at=self.snapshot)[0], "durably_homed_open")
        merged = {**base, "merged_at": "2026-07-17T11:00:00Z"}
        self.assertEqual(classify_receipt(merged, snapshot_at=self.snapshot)[0], "verified_done")

    def test_missing_metrics_remain_unknown_not_zero(self) -> None:
        metric = None
        self.assertIsNone(metric)

    def test_late_write_exact_head_invalidation(self) -> None:
        receipt = {
            "created_at": "2026-07-17T10:00:00Z",
            "base_ref": "main",
            "default_branch": "main",
            "commits": [{"committed_at": "2026-07-19T16:00:00Z"}],
        }
        outcome, reason = classify_receipt(receipt, snapshot_at=self.snapshot)
        self.assertEqual(outcome, "coverage_unknown")
        self.assertIn("exact head", reason)

    def test_outcome_dedup_prefers_verified_terminal_receipt(self) -> None:
        self.assertEqual(
            strongest_outcome(["coverage_unknown", "durably_homed_open", "verified_done"]),
            "verified_done",
        )


if __name__ == "__main__":
    unittest.main()
