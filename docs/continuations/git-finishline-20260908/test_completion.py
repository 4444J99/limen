"""Small synthetic counterexamples for the recovery acceptance boundary."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("completion", Path(__file__).with_name("verify-completion.py"))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.head = "a" * 40
        self.expected = {"stash:0": "b" * 40}
        proof = self.write("predicate", {"head": self.head, "repository": "owner/repo",
                            "predicate_id": "runtime", "exit_code": 0, "executed": True})
        delivery = self.write("delivery", {"atom_id": "A", "repository": "owner/repo",
            "default_generation": self.head, "status": "delivered", "landing_kind": "merged_pr",
            "reachable_from_default": True, "implemented_head": self.head,
            "predicates": [{"id": "runtime", "receipt": proof}]})
        self.data = {"integration_generations": {"owner/repo": self.head},
            "sources": [{"source_id": "stash:0", "object": "b" * 40, "atom_ids": ["A"],
                "inspection": dict.fromkeys(("tracked", "index", "untracked", "requests", "reviews"), "assessed")}],
            "atoms": [{"atom_id": "A", "timestamp": "2026-09-08T00:00:00Z", "source_ids": ["stash:0"],
                "unresolved_findings": [], "required_predicates": ["runtime"], "delivery": delivery,
                "outcome": {"disposition": "done", "owner": "owner/repo", "assessed_at": "2026-09-08T01:00:00Z",
                    "evidence": [{"kind": "predicate_receipt", "ref": proof["ref"],
                        "artifact_sha256": proof["sha256"], "predicate": "runtime", "result": "pass",
                        "verified_at": "2026-09-08T01:00:00Z", "subject_atom_ids": ["A"],
                        "owner": "owner/repo", "verifier": "local_predicate", "exit_code": 0}]}}]}
        landing = {"kind": "github_pr", "ref": "https://github.com/owner/repo/pull/1",
            "predicate": "merged and reachable", "result": "pass", "verified_at": "2026-09-08T01:00:00Z",
            "owner": "owner/repo", "subject_atom_ids": ["A"], "verifier": "github_api",
            "state": "merged", "head_sha": self.head, "merge_commit_sha": self.head,
            "reachable_from_default": True}
        receipt = self.write("landing", {"schema": "limen.github-verification.v1", "exit_code": 0,
                                         "evidence": copy.deepcopy(landing)})
        landing.update(verification_receipt_ref=receipt["ref"], verification_receipt_sha256=receipt["sha256"])
        self.data["atoms"][0]["outcome"]["evidence"].append(landing)
        self.lineage = dict.fromkeys(("source-findings", "review-findings", "branch-pr-findings"), "d" * 64)
        self.data.update(count_status="reconciled", private_extraction_sha256=self.lineage)
        self.data["atoms"][0]["candidate_ids"] = ["C1"]
        self.data["candidate_inventory"] = self.write("candidates", {
            "private_extraction_sha256": self.lineage,
            "candidates": [{"candidate_id": "C1", "source_ids": ["stash:0"]}]})

    def write(self, name, value):
        path = self.root / "docs" / (name + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(value))
        subprocess.run(["git", "-C", str(self.root), "add", str(path)], check=True)
        return {"ref": path.relative_to(self.root).as_posix(), "sha256": C.digest(path)}

    def result(self, data=None):
        return C.check(self.data if data is None else data, self.expected, self.root)

    def test_positive_and_unchanged_repeat(self):
        self.assertEqual(self.result()["status"], "PASS")
        self.assertEqual(self.result(), self.result())

    def test_missing_source(self):
        self.data["sources"] = []
        self.assertEqual(self.result()["status"], "FAIL")

    def test_omitted_candidate_despite_reciprocal_source_coverage(self):
        self.data["atoms"][0]["candidate_ids"] = []
        self.assertEqual(self.result()["status"], "FAIL")

    def test_provisional_count_is_not_completion(self):
        self.data["count_status"] = "provisional"
        self.assertEqual(self.result()["status"], "FAIL")

    def test_stale_extraction_and_missing_lineage(self):
        self.data["private_extraction_sha256"] = "e" * 64
        self.assertEqual(self.result()["status"], "FAIL")
        self.data["private_extraction_sha256"] = self.lineage
        self.data["atoms"][0]["source_ids"] = []
        self.assertEqual(self.result()["status"], "FAIL")

    def test_stale_evidence(self):
        (self.root / "docs/predicate.json").write_text("{}")
        self.assertEqual(self.result()["status"], "FAIL")

    def test_malformed_and_empty_extraction(self):
        for candidates in (None, {}, [], [None], [{"candidate_id": [], "source_ids": []}],
                           [{"candidate_id": "C1", "source_ids": []}],
                           [{"candidate_id": "C1", "source_ids": ["outside"]}]):
            with self.subTest(candidates=candidates):
                self.data["candidate_inventory"] = self.write("candidates", {
                    "private_extraction_sha256": self.lineage, "candidates": candidates})
                self.assertEqual(self.result()["status"], "FAIL")

    def test_missing_digest_on_both_sides_is_not_lineage(self):
        self.data.pop("private_extraction_sha256")
        self.data["candidate_inventory"] = self.write("candidates", {
            "candidates": [{"candidate_id": "C1", "source_ids": ["stash:0"]}]})
        self.assertEqual(self.result()["status"], "FAIL")

    def test_independent_candidate_denominator(self):
        self.assertEqual(C.check(self.data, self.expected, self.root, candidate_count=2)["status"], "FAIL")

    def test_malformed_top_level_inventory(self):
        for data in ([], {"atoms": None}, {"sources": [None]}, {"atoms": [{"atom_id": []}]}):
            with self.subTest(data=data):
                self.assertEqual(self.result(data)["status"], "FAIL")

    def test_malformed_nested_evidence(self):
        for field in ("outcome", "source_ids", "candidate_ids", "delivery"):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["atoms"][0][field] = None
                self.assertEqual(self.result(data)["status"], "FAIL")

    def test_stale_generation(self):
        self.data["integration_generations"]["owner/repo"] = "c" * 40
        self.assertEqual(self.result()["status"], "FAIL")

    def test_prose_landing_without_verified_remote_receipt(self):
        self.data["atoms"][0]["outcome"]["evidence"].pop()
        self.assertEqual(self.result()["status"], "FAIL")

    def test_archive_owner_draft_and_closed_unmerged_are_not_delivery(self):
        for kind in ("archive", "owner", "draft", "closed_unmerged"):
            with self.subTest(kind=kind):
                path = self.root / "docs/delivery.json"
                value = json.loads(path.read_text())
                value["landing_kind"] = kind
                self.data["atoms"][0]["delivery"] = self.write("delivery", value)
                self.assertEqual(self.result()["status"], "FAIL")

    def test_false_supersession(self):
        original = self.data["atoms"][0]
        successor = copy.deepcopy(original)
        successor.update(atom_id="B", timestamp="2026-09-08T02:00:00Z", predecessor_ids=["A"])
        successor["outcome"] = {"disposition": "unassessed"}
        original["outcome"].update(disposition="superseded", successor_atom_id="B")
        self.data["atoms"].append(successor)
        self.data["sources"][0]["atom_ids"].append("B")
        self.assertEqual(self.result()["status"], "FAIL")

    def test_unresolved_findings_and_missing_runtime(self):
        self.data["atoms"][0]["unresolved_findings"] = ["F1"]
        self.assertEqual(self.result()["status"], "FAIL")
        self.data["atoms"][0]["unresolved_findings"] = []
        self.data["atoms"][0]["required_predicates"].append("rendered_output")
        self.assertEqual(self.result()["status"], "FAIL")


class ResumeAdmissionTests(unittest.TestCase):
    def test_denial_never_executes_a_gate(self):
        spec = importlib.util.spec_from_file_location("resume", Path(__file__).with_name("resume-heavy.py"))
        resume = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(resume)

        class Denied(RuntimeError):
            pass

        @contextmanager
        def deny(**kwargs):
            raise Denied("synthetic pressure")
            yield

        runner = SimpleNamespace(
            load_registry=lambda: {"gates": {g: {"serialize": g != "worker-check"} for g in
                ["worker-check", "pytest-cli", "pytest-api", "web-build"]}},
            heavy_admission=deny, HostAdmissionFailure=Denied, run_gate_wave=Mock())
        fake_spec = SimpleNamespace(name="synthetic_recovery_runner", loader=SimpleNamespace(exec_module=lambda m: None))
        with patch.object(resume.subprocess, "run"), patch.object(resume.subprocess, "check_output", return_value=""), \
                patch.object(resume.os, "chdir"), \
                patch.object(resume.importlib.util, "spec_from_file_location", return_value=fake_spec), \
                patch.object(resume.importlib.util, "module_from_spec", return_value=runner):
            self.assertEqual(resume.main(), 75)
        runner.run_gate_wave.assert_not_called()


if __name__ == "__main__":
    unittest.main()
