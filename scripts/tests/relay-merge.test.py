"""Adversarial transaction tests. No network or production credential use."""

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import _relay_merge as relay

B, H, M, L = (c * 40 for c in "abcd")
APP = 812345


def readbacks():
    config = relay.configuration(APP)
    protection = config["branch_protection"]
    for key in (
        "enforce_admins",
        "required_conversation_resolution",
        "required_linear_history",
        "allow_force_pushes",
        "allow_deletions",
    ):
        protection[key] = {"enabled": protection[key]}
    ruleset = config["update_ruleset"]
    ruleset.update(source_type="Repository", source=relay.REPOSITORY)
    return protection, ruleset


class FakeGitHub:
    def __init__(self):
        self.protection, self.ruleset = readbacks()
        self.base, self.head, self.merge = B, H, M
        self.parents = [B, H]
        self.events = []
        self.landed = False
        self.producer = APP
        self.after_success = lambda: None
        self.auto_merge = None

    def __call__(self, path, method="GET", body=None):
        self.events.append((path, method, copy.deepcopy(body)))
        if path.endswith("/protection"):
            return self.protection
        if "/rulesets/" in path:
            return self.ruleset
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": self.base}}
        if path.endswith("/git/ref/pull/1/merge"):
            return {"object": {"sha": self.merge}}
        if "/git/commits/" in path:
            return {"parents": [{"sha": p} for p in self.parents]}
        if path.endswith("/check-runs"):
            return {"id": 42, "app": {"id": self.producer}, "head_sha": body["head_sha"], "name": body["name"]}
        if path.endswith("/check-runs/42"):
            if body.get("conclusion") == "success":
                self.after_success()
            return {}
        if path.endswith("/pulls/1/merge"):
            # Model documented server enforcement, not a proof of GitHub behavior.
            if self.base != B or self.head != body["sha"]:
                return {"merged": False}
            self.landed = True
            return {"merged": True, "sha": L}
        if path.endswith("/pulls/1"):
            return {
                "number": 1,
                "state": "closed" if self.landed else "open",
                "draft": False,
                "base": {"ref": "main", "repo": {"id": relay.REPOSITORY_ID}},
                "head": {"sha": self.head, "repo": {"full_name": relay.REPOSITORY}},
                "auto_merge": self.auto_merge,
                "merged": self.landed,
                "merge_commit_sha": L if self.landed else None,
            }
        raise AssertionError(path)

    def merges(self):
        return [e for e in self.events if e[1] == "PUT"]


class Transactions(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()

    def run_transaction(self, evaluate=lambda candidate: "e" * 64):
        return relay.transact(self.api, 1, H, APP, 123, evaluate)

    def test_good_control_evaluates_once_merges_once_consumes(self):
        calls = []
        result = self.run_transaction(lambda candidate: calls.append(candidate) or "e" * 64)
        self.assertEqual(result["landed"], L)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.api.merges()), 1)
        self.assertEqual(self.api.events[-1][2]["conclusion"], "failure")
        posted = next(e[2] for e in self.api.events if e[1] == "POST")
        self.assertEqual(posted["head_sha"], M)
        self.assertNotEqual(posted["head_sha"], H)

    def test_failed_evaluator_never_merges_despite_old_success(self):
        def fail(candidate):
            raise relay.Hold("policy failed; historical passing checks are irrelevant")

        with self.assertRaises(relay.Hold):
            self.run_transaction(fail)
        self.assertEqual(self.api.merges(), [])
        self.assertEqual(self.api.events[-1][2]["conclusion"], "failure")

    def test_changed_head_base_or_merge_during_evaluation(self):
        for field in ("head", "base", "merge"):
            with self.subTest(field=field):
                self.api = FakeGitHub()

                def changed(candidate, field=field):
                    setattr(self.api, field, "f" * 40)
                    return "e" * 64

                with self.assertRaises(relay.Hold):
                    self.run_transaction(changed)
                self.assertEqual(self.api.merges(), [])

    def test_changed_base_or_head_after_final_read_server_rejects(self):
        for field in ("base", "head"):
            with self.subTest(field=field):
                self.api = FakeGitHub()
                self.api.after_success = lambda field=field: setattr(self.api, field, "f" * 40)
                with self.assertRaises(relay.Hold):
                    self.run_transaction()
                self.assertEqual(len(self.api.merges()), 1)
                self.assertFalse(self.api.landed)

    def test_shared_app_cannot_take_custody(self):
        self.api.producer = 15368
        with self.assertRaises(relay.Hold):
            self.run_transaction()
        self.assertEqual(self.api.merges(), [])

    def test_wrong_parent_order_and_stale_synthetic_commit(self):
        for parents in ([H, B], [B], ["f" * 40, H]):
            self.api.parents = parents
            with self.assertRaises(relay.Hold):
                self.run_transaction()
            self.assertEqual(self.api.merges(), [])

    def test_no_queue_or_auto_merge(self):
        self.api.auto_merge = {"enabled_by": {"login": "candidate"}}
        with self.assertRaises(relay.Hold):
            self.run_transaction()
        self.assertEqual(self.api.merges(), [])

    def test_readback_outage_has_no_effect(self):
        with self.assertRaises(PermissionError):
            relay.transact(lambda *a: (_ for _ in ()).throw(PermissionError()), 1, H, APP, 123, lambda c: "e" * 64)

    def test_policy_rerun_notifications_are_not_inputs(self):
        self.run_transaction()
        self.assertFalse(any("/actions/" in e[0] or "statuses" in e[0] for e in self.api.events))

    def test_enforcement_tampering_during_evaluation(self):
        def tamper(candidate):
            self.api.ruleset["enforcement"] = "disabled"
            return "e" * 64

        with self.assertRaises(relay.Hold):
            self.run_transaction(tamper)
        self.assertEqual(self.api.merges(), [])


class Controls(unittest.TestCase):
    def test_invalid_ids(self):
        for value in (0, -1, True, 15368, 2**53, "812345"):
            with self.subTest(value=value), self.assertRaises(relay.Hold):
                relay.configuration(value)

    def test_weak_settings(self):
        mutations = [
            lambda p, r: p["required_status_checks"].update(strict=False),
            lambda p, r: p["required_status_checks"].update(checks=[]),
            lambda p, r: p["enforce_admins"].update(enabled=False),
            lambda p, r: p["allow_force_pushes"].update(enabled=True),
            lambda p, r: p["required_pull_request_reviews"].update(required_approving_review_count=0),
            lambda p, r: p["required_pull_request_reviews"].update(require_last_push_approval=False),
            lambda p, r: p["required_pull_request_reviews"].update(bypass_pull_request_allowances={"users": [1]}),
            lambda p, r: r.update(enforcement="evaluate"),
            lambda p, r: r["conditions"]["ref_name"].update(exclude=["refs/heads/main"]),
            lambda p, r: r["bypass_actors"][0].update(bypass_mode="always"),
            lambda p, r: r["bypass_actors"].append(
                {"actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "always"}
            ),
            lambda p, r: r["rules"].append({"type": "required_status_checks"}),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                p, r = readbacks()
                mutate(p, r)
                with self.assertRaises(relay.Hold):
                    relay.verify_controls(p, r, APP)

    def test_missing_deployment_never_invokes_api(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(sys, "argv", ["relay", "--pr", "1", "--expected-head", H]),
            patch.object(relay, "GitHub") as api,
        ):
            self.assertEqual(relay.main(), 2)
            api.assert_not_called()


class Routing(unittest.TestCase):
    def test_merge_drain_cannot_fall_back_to_generic_merge(self):
        spec = importlib.util.spec_from_file_location("merge_drain_relay_test", SCRIPTS / "merge-drain.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with (
            patch.object(module, "merge_prohibition", return_value=None),
            patch.object(module.subprocess, "run", side_effect=OSError),
            patch.object(module, "gh") as gh,
        ):
            self.assertEqual(module.merge(relay.REPOSITORY, 1, H, "direct"), "FAILED")
            self.assertEqual(module.merge(relay.REPOSITORY, 1, H, "queue"), "REFUSED")
            gh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
