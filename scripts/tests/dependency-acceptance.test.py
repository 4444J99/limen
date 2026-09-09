"""Adversarial admission probes: observations can route review, never merge."""

import base64
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _dependency_acceptance as admission

B, H, M = (c * 40 for c in "abc")
REPO = "organvm-vii-kerygma/portfolio"
WORKFLOW = ".github/workflows/ci.yml"
PIN = "d" * 40
LOCK_BEFORE = b'{"lockfileVersion":3,"packages":{"":{},"node_modules/pkg":{"version":"1.0.0"}}}'
LOCK = b'{"lockfileVersion":3,"packages":{"":{},"node_modules/pkg":{"version":"1.0.1"}}}'
LOCK_BEFORE_SHA = hashlib.sha1(f"blob {len(LOCK_BEFORE)}\0".encode() + LOCK_BEFORE).hexdigest()
LOCK_SHA = hashlib.sha1(f"blob {len(LOCK)}\0".encode() + LOCK).hexdigest()
POLICY = {
    "repository_id": 123,
    "base_ref": "main",
    "dependabot_actor_id": 456,
    "package_manager": "npm",
    "workflow_path": WORKFLOW,
    "trusted_files": {WORKFLOW: PIN, "scripts/dependency-evidence.mjs": PIN},
    "lockfiles": ["package-lock.json"],
    "reviewer": {"login": "review-bot[bot]", "id": 789},
    "required_workflows": [
        {
            "path": WORKFLOW,
            "jobs": {"Dependency evidence": ["Frozen install", "Collect"]},
            "checkout_jobs": ["Dependency evidence"],
        }
    ],
}


def make_zip(data, name="dependency-evidence.json"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, data)
    return stream.getvalue()


class Fixture:
    def __init__(self):
        self.policy = copy.deepcopy(POLICY)
        self.base, self.head, self.merge = B, H, M
        self.parents = [B, H]
        self.calls = []
        self.pr = {
            "number": 1,
            "state": "open",
            "draft": False,
            "auto_merge": None,
            "changed_files": 2,
            "base": {"repo": {"id": 123, "full_name": REPO}, "ref": "main"},
            "head": {"sha": H, "repo": {"id": 123}},
            "user": {"id": 456, "login": "dependabot[bot]", "type": "Bot"},
        }
        self.files = [{"filename": name, "status": "modified"} for name in ("package.json", "package-lock.json")]
        self.run = {
            "id": 100,
            "run_number": 9,
            "run_attempt": 1,
            "path": WORKFLOW,
            "event": "pull_request",
            "head_sha": H,
            "status": "completed",
            "conclusion": "success",
            "repository": {"id": 123, "full_name": REPO},
            "head_repository": {"id": 123},
            "updated_at": "2026-09-09T00:00:00Z",
        }
        self.job = {
            "id": 200,
            "run_id": 100,
            "run_attempt": 1,
            "head_sha": H,
            "name": "Dependency evidence",
            "status": "completed",
            "conclusion": "success",
            "steps": [
                {"name": name, "status": "completed", "conclusion": "success"} for name in ("Frozen install", "Collect")
            ],
        }
        self.receipt = {
            "schema": admission.SCHEMA,
            "repository": REPO,
            "base_sha": B,
            "head_sha": H,
            "tested_sha": M,
            "workflow_sha": M,
            "workflow_path": WORKFLOW,
            "run_id": "100",
            "run_attempt": "1",
            "lockfile_sha256": {"package-lock.json": hashlib.sha256(LOCK).hexdigest()},
            "graph": admission.graph_delta(json.loads(LOCK_BEFORE), json.loads(LOCK), "package-lock.json"),
            "advisories": {
                "status": "complete",
                **{key: [] for key in ("base", "head", "introduced", "resolved", "remaining", "errors")},
            },
            "exceptions": [],
            "route": "delegated-review",
        }
        self.pin = PIN
        self.log = f"2026-09-09T00:00:00.0000000Z [command]/usr/bin/git log -1 --format=%H\n2026-09-09T00:00:00.0000000Z '{M}'\n"
        self.after_download = lambda: None
        self.archive_override = None
        self.artifact_override = {}

    def raw(self):
        return self.archive_override or make_zip(json.dumps(self.receipt))

    def api(self, path):
        self.calls.append(path)
        if path.endswith("/pulls/1"):
            return copy.deepcopy(self.pr)
        if "/pulls/1/files?" in path:
            return self.files
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": self.base}}
        if path.endswith("/git/ref/pull/1/merge"):
            return {"object": {"sha": self.merge}}
        if "/git/commits/" in path:
            return {"parents": [{"sha": value} for value in self.parents]}
        if "/contents/" in path:
            name = path.split("/contents/")[1].split("?")[0]
            digest = LOCK_BEFORE_SHA if f"ref={B}" in path else LOCK_SHA
            return {"type": "file", "path": name, "sha": digest if name == "package-lock.json" else self.pin}
        if "/git/blobs/" in path:
            data = LOCK_BEFORE if path.endswith(LOCK_BEFORE_SHA) else LOCK
            return {"encoding": "base64", "size": len(data), "content": base64.b64encode(data).decode()}
        if "/actions/runs?" in path:
            return {"total_count": 1, "workflow_runs": [copy.deepcopy(self.run)]}
        if path.endswith("/actions/runs/100"):
            return copy.deepcopy(self.run)
        if "/jobs?" in path:
            return {"total_count": 1, "jobs": [copy.deepcopy(self.job)]}
        if "/artifacts?" in path:
            artifact = {
                "id": 300,
                "name": "dependency-evidence-100-1",
                "size_in_bytes": len(self.raw()),
                "expired": False,
                "digest": "sha256:" + hashlib.sha256(self.raw()).hexdigest(),
                "workflow_run": {"id": 100, "head_sha": H, "repository_id": 123, "head_repository_id": 123},
            }
            artifact.update(self.artifact_override)
            return {"total_count": 1, "artifacts": [artifact]}
        raise AssertionError(path)

    def archive(self, repository, artifact_id):
        assert repository == REPO and artifact_id == 300
        data = self.raw()
        self.after_download()
        return data

    def logs(self, repository, job_id):
        assert repository == REPO and job_id == 200
        return self.log

    def evaluate(self):
        return admission.evaluate(self.api, self.archive, REPO, 1, H, self.policy, self.logs)

    def gh(self, args, timeout=60, binary=False):
        assert args[0] == "api"
        path = args[1]
        if path.endswith("/zip"):
            return subprocess.CompletedProcess(args, 0, self.archive(REPO, 300))
        if path.endswith("/logs"):
            return subprocess.CompletedProcess(args, 0, self.logs(REPO, 200))
        return subprocess.CompletedProcess(args, 0, json.dumps(self.api(path)))


class EvidenceAdmission(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def test_healthy_routes_review_without_merge_authority(self):
        result = self.f.evaluate()
        self.assertEqual(result["route"], "delegated-review")
        self.assertFalse(result["automatic_acceptance"])
        self.assertEqual(result["reviewer"]["id"], 789)
        self.assertFalse(any("check-runs" in path for path in self.f.calls))

    def test_same_name_wrong_workflow_is_rejected(self):
        self.f.run["path"] = ".github/workflows/forgery.yml"
        with self.assertRaisesRegex(admission.Hold, "trusted-workflow-run-missing"):
            self.f.evaluate()

    def test_wrong_event_repository_attempt_or_job(self):
        for target, field, value in (
            ("run", "event", "push"),
            ("run", "head_repository", {"id": 999}),
            ("run", "head_sha", B),
            ("job", "run_attempt", 2),
            ("job", "head_sha", B),
            ("job", "conclusion", "skipped"),
        ):
            with self.subTest(target=target, field=field):
                self.f = Fixture()
                getattr(self.f, target)[field] = value
                with self.assertRaises(admission.Hold):
                    self.f.evaluate()

    def test_source_pin_drift(self):
        self.f.pin = "e" * 40
        with self.assertRaisesRegex(admission.Hold, "executable-pin-drift"):
            self.f.evaluate()

    def test_stale_or_candidate_checkout_is_rejected(self):
        for wrong in (B, H):
            self.f.log = self.f.log.replace(M, wrong)
            with self.assertRaisesRegex(admission.Hold, "checkout-revision-unproven"):
                self.f.evaluate()
            self.f = Fixture()

    def test_missing_or_forged_extra_checkout_log_is_rejected(self):
        for log in ("", self.f.log + self.f.log):
            self.f.log = log
            with self.assertRaises(admission.Hold):
                self.f.evaluate()

    def test_skipped_frozen_install_is_not_success(self):
        self.f.job["steps"][0]["conclusion"] = "skipped"
        with self.assertRaisesRegex(admission.Hold, "required-step-not-successful"):
            self.f.evaluate()

    def test_advanced_base_is_not_current_test_merge(self):
        self.f.base = "e" * 40
        with self.assertRaisesRegex(admission.Hold, "stale-test-merge"):
            self.f.evaluate()

    def test_base_race_during_archive_read(self):
        self.f.after_download = lambda: setattr(self.f, "base", "e" * 40)
        with self.assertRaises(admission.Hold):
            self.f.evaluate()

    def test_rerun_during_archive_read(self):
        self.f.after_download = lambda: self.f.run.update(run_attempt=2, status="in_progress", conclusion=None)
        with self.assertRaises(admission.Hold):
            self.f.evaluate()

    def test_receipt_wrong_revision_or_attempt(self):
        for field in ("base_sha", "head_sha", "tested_sha", "workflow_sha", "run_attempt"):
            with self.subTest(field=field):
                self.f = Fixture()
                self.f.receipt[field] = "e" * 40
                with self.assertRaises(admission.Hold):
                    self.f.evaluate()

    def test_advisory_errors_or_introductions_fail_closed(self):
        for field, value in (("status", "unavailable"), ("errors", ["offline"]), ("introduced", ["GHSA-new"])):
            with self.subTest(field=field):
                self.f = Fixture()
                self.f.receipt["advisories"][field] = value
                with self.assertRaises(admission.Hold):
                    self.f.evaluate()

    def test_major_or_unusual_policy_exception_does_not_route(self):
        self.f.receipt.update(route="exception", exceptions=["major-version-change"])
        with self.assertRaises(admission.Hold):
            self.f.evaluate()

    def test_wrong_lockfile_digest(self):
        self.f.receipt["lockfile_sha256"]["package-lock.json"] = "e" * 64
        with self.assertRaisesRegex(admission.Hold, "lockfile-digest"):
            self.f.evaluate()

    def test_expired_wrong_digest_and_wrong_run_artifacts(self):
        for mutation in (
            {"expired": True},
            {"digest": "sha256:" + "e" * 64},
            {"workflow_run": {"id": 999, "head_sha": H, "repository_id": 123, "head_repository_id": 123}},
        ):
            self.f.artifact_override = mutation
            with self.assertRaises(admission.Hold):
                self.f.evaluate()

    def test_archive_path_traversal_duplicate_keys_and_bombs(self):
        invalid = (
            make_zip("{}", "../dependency-evidence.json"),
            make_zip('{"schema":1,"schema":2}'),
            make_zip("x" * (admission.MAX_JSON + 1)),
        )
        for archive in invalid:
            with self.subTest(size=len(archive)), self.assertRaises(admission.Hold):
                admission.read_evidence_archive(archive)

    def test_missing_policy_and_uninstalled_policy_hold(self):
        result = admission.inspect_candidate(REPO, 1, H, self.f.gh)
        self.assertEqual(result["reasons"], ["trust-policy-unconfigured"])
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "policy.json"
            file.write_text(json.dumps({"schema": admission.TRUST_SCHEMA, "installed": False}))
            result = admission.inspect_candidate(REPO, 1, H, self.f.gh, file)
        self.assertEqual(result["reasons"], ["trust-policy-not-installed"])

    def test_source_pr_can_be_classified_without_trust_config(self):
        self.f.pr["user"]["login"] = "maintainer"
        self.f.pr["changed_files"] = 1
        self.f.files = [{"filename": "src/app.ts", "status": "modified"}]
        self.assertEqual(admission.inspect_candidate(REPO, 1, H, self.f.gh)["route"], "not-dependency")

    def test_dependency_author_does_not_bypass_lane(self):
        self.f.pr["user"]["login"] = "maintainer"
        self.assertEqual(admission.inspect_candidate(REPO, 1, H, self.f.gh)["route"], "exception")

    def test_incomplete_changed_files_and_mixed_source_changes_hold(self):
        for files in ([{"filename": "src/app.ts"}], self.f.files + [{"filename": "src/app.ts"}]):
            self.f.files = files
            self.assertEqual(admission.inspect_candidate(REPO, 1, H, self.f.gh)["route"], "exception")

    def test_case_variants_and_legacy_alias_remain_in_dependency_lane(self):
        for repository in (REPO.upper(), "Organvm-Vii-Kerygma/Portfolio", "4444J99/portfolio", "4444j99/PORTFOLIO"):
            with self.subTest(repository=repository):
                result = admission.inspect_candidate(repository, 1, H, self.f.gh)
                self.assertEqual(result["reasons"], ["trust-policy-unconfigured"])

    def test_source_rename_disguised_as_manifest_is_exception(self):
        self.f.files[0].update(status="renamed", previous_filename="src/config.json")
        result = admission.inspect_candidate(REPO, 1, H, self.f.gh)
        self.assertEqual(result["reasons"], ["dependency-file-addition-removal-or-rename"])

    def test_receipt_cannot_hide_actual_dependency_graph(self):
        self.f.receipt["graph"]["changed"][0]["before"]["version"] = "1.0.5"
        with self.assertRaisesRegex(admission.Hold, "dependency-graph-differs-from-source"):
            self.f.evaluate()

    def test_high_advisory_cannot_claim_routine(self):
        self.f.receipt["advisories"]["head"] = [{"severity": "high"}]
        with self.assertRaisesRegex(admission.Hold, "high-or-critical-advisories-remain"):
            self.f.evaluate()

    def test_full_cli_adapter_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "policy.json"
            file.write_text(
                json.dumps({"schema": admission.TRUST_SCHEMA, "installed": True, "repositories": {REPO: self.f.policy}})
            )
            result = admission.inspect_candidate(REPO, 1, H, self.f.gh, file)
        self.assertEqual(result["route"], "delegated-review")

    def test_unconfigured_or_author_reviewer_holds(self):
        for reviewer in (None, {"login": "dependabot[bot]", "id": 456}):
            self.f.policy["reviewer"] = reviewer
            with self.assertRaises(admission.Hold):
                self.f.evaluate()


if __name__ == "__main__":
    unittest.main()
