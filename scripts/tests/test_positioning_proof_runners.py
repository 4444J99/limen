import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts/tests/fixtures/positioning-proof"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECEIPT = load_module("positioning_flagship_receipt", ROOT / "scripts/positioning-flagship-receipt.py")
COST = load_module(
    "positioning_cost_failure_reproduction",
    ROOT / "scripts/positioning-cost-failure-reproduction.py",
)


def attach_origin(repository: Path, remote_root: Path) -> Path:
    remote = remote_root / "example" / "synthetic.git"
    remote.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=remote, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repository, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=repository, check=True)
    canonical = "https://github.com/example/synthetic.git"
    subprocess.run(
        ["git", "config", f"url.{remote.as_uri()}.insteadOf", canonical],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "remote", "set-url", "origin", canonical], cwd=repository, check=True)
    return remote


def run_request(request: dict[str, object]) -> dict[str, object]:
    repository = Path(str(request["repository_path"]))
    return RECEIPT.run_request(
        request,
        canonical_remote_lookup=lambda _repository: RECEIPT._run_git(
            repository,
            ["ls-remote", "--symref", "--exit-code", "origin", "HEAD"],
        ),
    )


class PositioningProofRunnerTest(unittest.TestCase):
    def test_canonical_remote_lookup_ignores_all_git_rewrite_surfaces(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        injected = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.file:///mirror.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
            "GIT_DIR": "/tmp/untrusted.git",
            "GIT_WORK_TREE": "/tmp/untrusted-tree",
        }
        with mock.patch.dict(os.environ, injected, clear=False):
            with mock.patch.object(RECEIPT.subprocess, "run", return_value=completed) as run:
                result = RECEIPT._run_canonical_remote("example/synthetic")
        self.assertIs(result, completed)
        argv = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(
            [
                "git",
                "ls-remote",
                "--symref",
                "--exit-code",
                "https://github.com/example/synthetic.git",
                "HEAD",
            ],
            argv,
        )
        self.assertEqual(Path("/"), options["cwd"])
        self.assertEqual("1", options["env"]["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual(os.devnull, options["env"]["GIT_CONFIG_GLOBAL"])
        self.assertNotIn("GIT_CONFIG_COUNT", options["env"])
        self.assertNotIn("GIT_DIR", options["env"])
        self.assertNotIn("GIT_WORK_TREE", options["env"])

    def test_cost_failure_fixture_reproduces_all_dimensions(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        result = COST.reproduce(payload)
        self.assertEqual("regenerated", result["status"])
        self.assertEqual(3, result["denominator"])
        self.assertEqual(1, result["terminal_states"]["failed"])
        self.assertEqual(1, result["terminal_states"]["failed_blocked"])
        self.assertEqual(5, len(result["dimensions"]))
        self.assertEqual(64, len(result["data_digest"]))

    def test_cost_failure_private_or_unknown_fields_fail_closed(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["rows"][0]["customer"] = "private"
        result = COST.reproduce(payload)
        self.assertEqual("withheld", result["status"])
        self.assertFalse(result["publication_eligible"])

    def test_cost_failure_unhashable_failure_classes_fail_closed(self) -> None:
        for failure_class in ({"code": "timeout"}, ["timeout"]):
            payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
            payload["rows"][1]["failure_class"] = failure_class
            result = COST.reproduce(payload)
            self.assertEqual("withheld", result["status"])
            self.assertTrue(any("reviewed public failure_class" in error for error in result["errors"]))

    def test_cost_failure_rows_must_fall_inside_an_ordered_window(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["rows"][0].pop("observed_at")
        payload["rows"][1]["observed_at"] = "2026-08-09T12:00:00Z"
        payload["window_start"] = "2026-08-07"
        payload["window_end"] = "2026-08-01"
        errors = COST.validate_sample(payload)
        self.assertIn("sample date window must be ordered", errors)
        self.assertIn("row 0 requires observed_at", errors)
        self.assertTrue(any("outside the declared window" in error for error in errors))

    def test_non_done_zero_cost_or_private_failure_class_is_withheld(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        failed = payload["rows"][1]
        for field in (
            "model_cost_usd",
            "human_minutes",
            "retry_count",
            "retry_cost_usd",
            "verification_cost_usd",
        ):
            failed[field] = 0
        failed["failure_class"] = "customer@example.invalid"
        result = COST.reproduce(payload)
        self.assertEqual("withheld", result["status"])
        self.assertTrue(any("reviewed public failure_class" in error for error in result["errors"]))
        self.assertTrue(any("positive measured cost/time" in error for error in result["errors"]))

    def test_non_done_explicit_unknown_withholds_publication(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        failed = payload["rows"][1]
        failed["model_cost_usd"] = None
        failed["model_cost_basis"] = "unknown"
        failed["human_minutes"] = None
        result = COST.reproduce(payload)
        self.assertEqual("withheld", result["status"])
        self.assertFalse(result["publication_eligible"])

    def test_exact_head_runner_passes_and_hashes_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", "print('synthetic pass')"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("current_pass", result["result"])
            self.assertEqual(head, result["exact_head"])
            self.assertEqual(head, result["remote_default_branch_head"])
            self.assertEqual("example/synthetic", result["origin_repository"])
            self.assertEqual(64, len(result["artifact_digest"]))

    def test_exact_head_runner_binds_origin_to_requested_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            subprocess.run(
                ["git", "remote", "set-url", "origin", "https://github.com/example/stale-mirror.git"],
                cwd=repository,
                check=True,
            )
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", "from pathlib import Path; Path('ran.txt').touch()"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("not_current", result["result"])
            self.assertEqual("example/stale-mirror", result["origin_repository"])
            self.assertTrue(any("origin does not identify" in error for error in result["errors"]))
            self.assertFalse((repository / "ran.txt").exists())

    def test_exact_head_mismatch_is_not_current(self) -> None:
        request = {
            "schema_version": RECEIPT.SCHEMA_VERSION,
            "flagship_id": "synthetic",
            "repository": "example/synthetic",
            "repository_path": str(ROOT),
            "default_branch": "main",
            "expected_head": "0" * 40,
            "predicate": {
                "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                "timeout_seconds": 10,
                "max_output_bytes": 4096,
            },
            "limitations": ["Synthetic fixture only."],
        }
        self.assertEqual("not_current", run_request(request)["result"])

    def test_exact_head_runner_rejects_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            (repository / "fixture.txt").write_text("dirty\n", encoding="utf-8")
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("not_current", result["result"])
            self.assertIn("tracked or untracked changes", result["errors"][0])

    def test_exact_head_runner_requires_default_branch_tip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "missing-default",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("not_current", result["result"])
            self.assertIn("default-branch tip", result["errors"][0])

    def test_exact_head_runner_bounds_output_and_records_spawn_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            base_request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "limitations": ["Synthetic fixture only."],
            }
            verbose = {
                **base_request,
                "predicate": {
                    "argv": [sys.executable, "-c", "import sys; sys.stdout.write('x' * 10000)"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 1024,
                },
            }
            bounded = run_request(verbose)
            self.assertEqual("current_fail", bounded["result"], bounded)
            self.assertEqual(1024, bounded["output_bytes"])
            self.assertIn("bounded output budget", bounded["errors"][0])
            missing = {
                **base_request,
                "predicate": {
                    "argv": ["/definitely/missing-positioning-predicate"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 1024,
                },
            }
            blocked = run_request(missing)
            self.assertEqual("blocked_external", blocked["result"])
            self.assertIn("predicate could not start", blocked["errors"][0])

    def test_remote_default_branch_advance_is_not_current(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            tempfile.TemporaryDirectory() as remote_temporary,
            tempfile.TemporaryDirectory() as peer_temporary,
        ):
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            remote = attach_origin(repository, Path(remote_temporary))
            peer = Path(peer_temporary) / "peer"
            subprocess.run(["git", "clone", "-q", "--branch", "main", str(remote), str(peer)], check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=peer, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=peer, check=True)
            (peer / "remote.txt").write_text("advanced\n", encoding="utf-8")
            subprocess.run(["git", "add", "remote.txt"], cwd=peer, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "advance remote"],
                cwd=peer,
                check=True,
            )
            subprocess.run(["git", "push", "-q", "origin", "main"], cwd=peer, check=True)
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("not_current", result["result"])
            self.assertIn("remote default-branch tip", result["errors"][0])

    def test_requested_branch_must_be_the_authoritative_remote_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            subprocess.run(["git", "branch", "feature"], cwd=repository, check=True)
            subprocess.run(["git", "push", "-q", "origin", "feature"], cwd=repository, check=True)
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "feature",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", "raise SystemExit(0)"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("not_current", result["result"])
            self.assertIn("authoritative remote default branch", result["errors"][0])
            self.assertEqual("main", result["remote_default_branch"])

    def test_post_predicate_remote_outage_is_blocked_external(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            remote = attach_origin(repository, Path(remote_temporary))
            offline = remote.with_name("synthetic-offline.git")
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [
                        sys.executable,
                        "-c",
                        f"import os; os.rename({str(remote)!r}, {str(offline)!r})",
                    ],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("blocked_external", result["result"])
            self.assertTrue(any("post-predicate remote default-branch tip" in error for error in result["errors"]))

    def test_post_predicate_mutation_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('fixture.txt').write_text('changed')",
                    ],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("not_current", result["result"])
            self.assertTrue(any("worktree changed" in error for error in result["errors"]))

    def test_inherited_predicate_pipe_fails_bounded_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [
                        sys.executable,
                        "-c",
                        "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], start_new_session=True); print('parent done')",
                    ],
                    "timeout_seconds": 1,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("current_fail", result["result"])
            self.assertTrue(any("live descendant" in error for error in result["errors"]))

    def test_redirected_predicate_descendant_is_terminated_before_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            child = "import time; from pathlib import Path; time.sleep(0.5); Path('late.txt').write_text('late')"
            parent = (
                "import subprocess,sys; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}], stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL, start_new_session=True); print('parent done')"
            )
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", parent],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("current_fail", result["result"])
            self.assertTrue(any("live descendant" in error for error in result["errors"]))
            time.sleep(0.7)
            self.assertFalse((repository / "late.txt").exists())

    def test_detached_predicate_descendant_is_terminated_before_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as remote_temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / "fixture.txt").write_text("synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            attach_origin(repository, Path(remote_temporary))
            grandchild = (
                "import time; from pathlib import Path; time.sleep(0.5); Path('detached-late.txt').write_text('late')"
            )
            child = (
                "import subprocess,sys; "
                f"subprocess.Popen([sys.executable,'-c',{grandchild!r}], stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL, start_new_session=True, env={})"
            )
            parent = (
                "import subprocess,sys; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}], stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL, start_new_session=True, env={}); print('parent done')"
            )
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": str(repository),
                "default_branch": "main",
                "expected_head": head,
                "predicate": {
                    "argv": [sys.executable, "-c", parent],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("current_fail", result["result"])
            self.assertTrue(any("live descendant" in error for error in result["errors"]))
            time.sleep(0.7)
            self.assertFalse((repository / "detached-late.txt").exists())


if __name__ == "__main__":
    unittest.main()
