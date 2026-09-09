"""Adversarial review-routing tests; all provider and notification effects are fake."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import _dependency_upkeep as upkeep

REPO = "organvm-vii-kerygma/portfolio"
HEAD = "a" * 40
EVIDENCE = {
    "route": "delegated-review",
    "head_sha": HEAD,
    "base_sha": "b" * 40,
    "reviewer": {"login": "review-agent[bot]", "id": 501},
}


class Provider:
    def __init__(self):
        self.calls = []
        self.requested = False
        self.reviewed = False
        self.review_state = "COMMENTED"
        self.review_history = None
        self.labels = []
        self.kind = "Bot"
        self.head = HEAD
        self.author = 999
        self.fail_request = False

    def __call__(self, args, timeout=60, binary=False):
        self.calls.append(args)
        if "POST" in args:
            if self.fail_request:
                return SimpleNamespace(returncode=1, stdout="", stderr="private diagnostics")
            self.requested = True
            value = {}
        elif args[1].startswith("users/"):
            value = {"id": 501, "login": "review-agent[bot]", "type": self.kind}
        elif "/reviews?" in args[1]:
            value = [{"user": {"id": 501}, "commit_id": HEAD, "state": self.review_state}] if self.reviewed else []
            if self.review_history is not None:
                value = [{"user": {"id": 501}, "commit_id": HEAD, "state": state} for state in self.review_history]
        else:
            value = {
                "state": "open",
                "draft": False,
                "labels": self.labels,
                "head": {"sha": self.head},
                "user": {"id": self.author},
                "requested_reviewers": [{"id": 501}] if self.requested else [],
            }
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr="")

    def mutations(self):
        return [args for args in self.calls if "POST" in args]


class Reviews(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()

    def request(self, evidence=EVIDENCE):
        with patch.object(upkeep, "inspect", return_value=evidence):
            return upkeep.request_review(REPO, 1, HEAD, self.provider)

    def test_request_is_quiet_independent_and_idempotent(self):
        self.assertEqual(self.request(), ("requested", []))
        self.assertEqual(self.request(), ("already-requested", []))
        self.assertEqual(len(self.provider.mutations()), 1)
        self.assertIn("/requested_reviewers", self.provider.mutations()[0][1])
        self.assertFalse(any("merge" in str(args) for args in self.provider.calls))

    def test_completed_exact_head_review_prevents_repeat(self):
        self.provider.reviewed = True
        self.assertEqual(self.request(), ("reviewed", []))
        self.assertEqual(self.provider.mutations(), [])

    def test_changes_requested_becomes_exception(self):
        self.provider.reviewed = True
        self.provider.review_state = "CHANGES_REQUESTED"
        self.assertEqual(self.request(), ("exception", ["review-changes-requested"]))
        self.assertEqual(self.provider.mutations(), [])

    def test_comment_and_rerequest_cannot_hide_denial(self):
        self.provider.requested = True
        self.provider.review_history = ["CHANGES_REQUESTED", "COMMENTED"]
        self.assertEqual(self.request(), ("exception", ["review-changes-requested"]))
        self.assertEqual(self.provider.mutations(), [])

    def test_later_approval_supersedes_denial(self):
        self.provider.review_history = ["CHANGES_REQUESTED", "APPROVED"]
        self.assertEqual(self.request(), ("reviewed", []))
        self.assertEqual(self.provider.mutations(), [])

    def test_active_human_label_prevents_dispatch_after_batch(self):
        self.provider.labels = [{"name": "lifecycle:active-human"}]
        self.assertEqual(self.request(), ("exception", ["review-lifecycle-hold"]))
        self.assertEqual(self.provider.mutations(), [])

    def test_missing_reviewer_fails_closed(self):
        result = self.request({"route": "delegated-review"})
        self.assertEqual(result, ("exception", ["reviewer-unconfigured"]))
        self.assertEqual(self.provider.calls, [])

    def test_human_identity_cannot_be_silently_selected(self):
        self.provider.kind = "User"
        self.assertEqual(self.request()[1], ["reviewer-identity-mismatch"])
        self.assertEqual(self.provider.mutations(), [])

    def test_candidate_author_cannot_review_itself(self):
        self.provider.author = 501
        self.assertEqual(self.request()[1], ["review-candidate-changed"])
        self.assertEqual(self.provider.mutations(), [])

    def test_changed_head_never_requests_review(self):
        self.provider.head = "c" * 40
        self.assertEqual(self.request()[1], ["review-candidate-changed"])
        self.assertEqual(self.provider.mutations(), [])

    def test_changed_attempt_or_base_before_request_is_exception(self):
        with patch.object(upkeep, "inspect", side_effect=[EVIDENCE, EVIDENCE | {"base_sha": "c" * 40}]):
            result = upkeep.request_review(REPO, 1, HEAD, self.provider)
        self.assertEqual(result[1], ["review-evidence-changed"])
        self.assertEqual(self.provider.mutations(), [])

    def test_ambiguous_request_is_not_reported_as_requested(self):
        self.provider.fail_request = True
        self.assertEqual(self.request()[1], ["review-request-unconfirmed"])
        self.assertEqual(len(self.provider.mutations()), 1)


class Drain(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("dependency_drain", SCRIPTS / "merge-drain.py")
        self.drain = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.drain)

    def test_dependency_without_lifecycle_label_routes_before_generic_gate(self):
        response = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"state": "OPEN", "isDraft": False, "headRefOid": HEAD, "labels": []}),
            stderr="",
        )
        with (
            patch.object(self.drain, "gh", return_value=response),
            patch.object(upkeep, "inspect", return_value=EVIDENCE),
        ):
            row = self.drain.assess((REPO, 1))
        self.assertEqual(row[2], "DEPS-REVIEW")

    def test_no_dependency_route_can_enter_generic_merge(self):
        for route in ("delegated-review", "exception", "unknown"):
            with (
                self.subTest(route=route),
                patch.object(self.drain, "merge_prohibition", return_value=None),
                patch.object(upkeep, "inspect", return_value={"route": route}),
                patch.object(self.drain, "gh", side_effect=AssertionError("unexpected merge")),
            ):
                self.assertEqual(self.drain.merge(REPO, 1, HEAD, "direct"), "REFUSED")

    def test_queued_dependency_does_not_claim_accepted_handoff(self):
        with (
            patch.object(self.drain, "merge_prohibition", return_value=None),
            patch.object(self.drain, "_queue_state", return_value={"state": "OPEN", "head": HEAD, "queued": True}),
            patch.object(upkeep, "inspect", return_value=EVIDENCE),
        ):
            self.assertEqual(self.drain.submit_one(REPO, 1, HEAD), 2)

    def test_exception_notification_identity_changes_with_reason(self):
        with patch.object(self.drain._notify, "emit_event_v1") as notify:
            self.drain.dependency_exception(REPO, 1, HEAD, ["stale-base"])
            self.drain.dependency_exception(REPO, 1, HEAD, ["failed-tests"])
        self.assertNotEqual(notify.call_args_list[0].kwargs["stable_id"], notify.call_args_list[1].kwargs["stable_id"])


if __name__ == "__main__":
    unittest.main()
