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
from datetime import datetime, timedelta, timezone
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
    "manifests": ["package.json"],
    "max_evidence_age_seconds": 86400,
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
        self.locks = {B: json.loads(LOCK_BEFORE), H: json.loads(LOCK), M: json.loads(LOCK)}
        self.blobs = {}
        self.nonregular_manifests = set()
        self.dereferenced_symlinks = set()
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
            "run_started_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
            "dependency_revision_sha": M,
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
        if "/git/trees/" in path:
            revision = path.split("/git/trees/")[1].split("?")[0]
            names = set(self.policy["trusted_files"]) | set(self.policy["manifests"]) | set(self.policy["lockfiles"])
            data = json.dumps(self.locks[revision], separators=(",", ":")).encode()
            digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            return {
                "truncated": False,
                "tree": [
                    {
                        "path": name,
                        "type": "blob",
                        "mode": "120000" if name in self.dereferenced_symlinks else "100644",
                        "sha": digest if name == "package-lock.json" else self.pin,
                    }
                    for name in names
                ],
            }
        if "/contents/" in path:
            name = path.split("/contents/")[1].split("?")[0]
            digest = self.pin
            if name == "package-lock.json":
                revision = path.split("?ref=")[1]
                data = json.dumps(self.locks[revision], separators=(",", ":")).encode()
                digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                self.blobs[digest] = data
            return {"type": "symlink" if name in self.nonregular_manifests else "file", "path": name, "sha": digest}
        if "/git/blobs/" in path:
            data = self.blobs[path.rsplit("/", 1)[-1]]
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
        for field in ("base_sha", "head_sha", "tested_sha", "dependency_revision_sha", "workflow_sha", "run_attempt"):
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
        self.assertEqual(self.inspect()["route"], "delegated-review")

    def inspect(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "policy.json"
            file.write_text(
                json.dumps({"schema": admission.TRUST_SCHEMA, "installed": True, "repositories": {REPO: self.f.policy}})
            )
            result = admission.inspect_candidate(REPO, 1, H, self.f.gh, file)
        return result

    def workspace(self):
        self.f.policy["manifests"].append("packages/core/package.json")
        for revision in (B, H, M):
            self.f.locks[revision]["packages"]["packages/core"] = {"name": "@scope/core", "version": "1.0.0"}
        data = json.dumps(self.f.locks[M], separators=(",", ":")).encode()
        self.f.receipt["lockfile_sha256"]["package-lock.json"] = hashlib.sha256(data).hexdigest()
        self.f.files[0]["filename"] = "packages/core/package.json"

    def test_existing_trusted_workspace_patch_routes(self):
        self.workspace()
        self.assertEqual(self.inspect()["route"], "delegated-review")

    def test_unknown_missing_nonregular_or_changed_workspace_inventory_holds(self):
        for case in ("unknown", "missing-root", "unlisted", "new", "nonregular"):
            with self.subTest(case=case):
                self.f = Fixture()
                self.workspace()
                if case == "unknown":
                    self.f.files[0]["filename"] = "unknown/package.json"
                elif case == "missing-root":
                    self.f.policy["manifests"].remove("package.json")
                elif case == "unlisted":
                    self.f.policy["manifests"].remove("packages/core/package.json")
                elif case == "new":
                    del self.f.locks[B]["packages"]["packages/core"]
                else:
                    self.f.nonregular_manifests.add("packages/core/package.json")
                self.assertEqual(self.inspect()["route"], "exception")

    def test_workspace_add_remove_rename_remains_exception(self):
        self.workspace()
        for status in ("added", "removed", "renamed"):
            self.f.files[0]["status"] = status
            self.assertEqual(self.inspect()["reasons"], ["dependency-file-addition-removal-or-rename"])

    def test_old_malformed_future_and_reversed_workflow_times_hold(self):
        now = datetime.now(timezone.utc)

        def stamp(moment):
            return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

        for change in (
            {"run_started_at": stamp(now - timedelta(days=2))},
            {"run_started_at": "not-a-time"},
            {"run_started_at": "2026-99-09T00:00:00Z"},
            {"updated_at": stamp(now + timedelta(minutes=1))},
            {"updated_at": stamp(now - timedelta(hours=1))},
        ):
            with self.subTest(change=change):
                self.f = Fixture()
                self.f.run.update(change)
                self.assertEqual(self.inspect()["route"], "exception")

    def test_artifact_generated_at_cannot_refresh_old_provider_run(self):
        self.f.run["run_started_at"] = "2020-01-01T00:00:00Z"
        self.f.receipt["generated_at"] = datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.inspect()["reasons"], ["dependency-evidence-expired"])

    def test_known_running_workflow_is_quiet_pending_but_failure_is_exception(self):
        for status in ("queued", "in_progress", "waiting"):
            self.f.run.update(status=status, conclusion=None)
            result = self.inspect()
            self.assertEqual(result["route"], "pending")
            self.assertFalse(result["automatic_acceptance"])
        self.f.run.update(status="completed", conclusion="failure")
        self.assertEqual(self.inspect()["route"], "exception")
        self.f.run.update(status="in_progress", conclusion=None, event="push")
        self.assertEqual(self.inspect()["route"], "exception")

    def test_extra_archive_member_is_not_part_of_primary_evidence(self):
        stream = io.BytesIO(self.f.raw())
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("audit-base-package-lock.json", "{}")
        with self.assertRaisesRegex(admission.Hold, "archive-member-count"):
            admission.read_evidence_archive(stream.getvalue())

    def test_contents_dereferenced_symlink_cannot_claim_regular_file(self):
        for name in (WORKFLOW, "package.json", "package-lock.json"):
            self.f = Fixture()
            self.f.dereferenced_symlinks.add(name)
            self.assertEqual(self.inspect()["reasons"], ["nonregular-policy-file"])

    def test_unconfigured_or_author_reviewer_holds(self):
        for reviewer in (None, {"login": "dependabot[bot]", "id": 456}):
            self.f.policy["reviewer"] = reviewer
            with self.assertRaises(admission.Hold):
                self.f.evaluate()


if __name__ == "__main__":
    unittest.main()
