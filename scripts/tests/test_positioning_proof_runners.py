import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from urllib.parse import quote
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
COST_INPUT_ARTIFACT = "scripts/tests/fixtures/positioning-proof/synthetic-cost-failure.json"
COST_REVIEW_ARTIFACT = "scripts/tests/fixtures/positioning-proof/independent-cost-failure-review.json"
COST_SOURCE_HEAD = "a" * 40
COST_RUNNER_BLOB = "b" * 40
COST_INPUT_BLOB = "c" * 40
COST_REVIEW_BLOB = "d" * 40


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
    flagship_key = request["flagship_id"] if isinstance(request.get("flagship_id"), str) else "synthetic"
    hermetic_contract = {
        "repository": request["repository"],
        "default_branch": request["default_branch"],
        "predicate": request["predicate"],
        "runtime_setup": {"mode": "none"},
    }
    hermetic_payload = {"exact_head_receipt_plan": {"flagship_predicates": {flagship_key: hermetic_contract}}}
    contract_environment = {
        "proof_contract_head": "a" * 40,
        "proof_contract_blob": "b" * 40,
        "proof_contract_sha256": "c" * 64,
    }
    with mock.patch.object(
        RECEIPT,
        "_proof_contract_snapshot",
        return_value=(hermetic_payload, contract_environment),
    ):
        return RECEIPT.run_request(
            request,
            canonical_remote_lookup=lambda _repository: RECEIPT._run_git(
                repository,
                ["ls-remote", "--symref", "--exit-code", "origin", "HEAD"],
            ),
        )


def independent_cost_review(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": COST.REVIEW_SCHEMA,
        "reviewer_class": "independent_model",
        "reviewer_identity": "chatgpt-codex-connector",
        "observed_at": "2026-08-08T12:00:00Z",
        "data_digest": COST._canonical_digest(payload),
        "population_digest": COST._canonical_digest(payload["population"]),
        "verdict": "publishable_public_safe",
        "limitations": ["Hermetic contract fixture only; not external publication authority."],
        "authority_receipt_url": None,
        "authority_receipt_sha256": None,
    }


def exact_cost_kwargs(payload: dict[str, object], review: dict[str, object] | None = None) -> dict[str, object]:
    exact_artifacts: dict[str, object] = {COST_INPUT_ARTIFACT: payload}
    if review is not None:
        exact_artifacts[COST_REVIEW_ARTIFACT] = review
    return {
        "source_head": COST_SOURCE_HEAD,
        "runner_blob": COST_RUNNER_BLOB,
        "input_blob": COST_INPUT_BLOB,
        "review_blob": COST_REVIEW_BLOB if review is not None else None,
        "exact_artifacts": exact_artifacts,
    }


def reproduce_cost(payload: dict[str, object], *, reviewed: bool = False) -> dict[str, object]:
    review = independent_cost_review(payload) if reviewed else None
    return COST.reproduce(
        payload,
        input_artifact=COST_INPUT_ARTIFACT,
        review_artifact=COST_REVIEW_ARTIFACT if review is not None else None,
        review_verdict=review,
        **exact_cost_kwargs(payload, review),
    )


def wait_for_recorded_process_exit(pid_path: Path, timeout_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not pid_path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not pid_path.exists():
        raise AssertionError(f"descendant did not record its pid at {pid_path}")
    pid = int(pid_path.read_text(encoding="utf-8"))
    exit_deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < exit_deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    raise AssertionError(f"descendant process {pid} remained live")


class PositioningProofRunnerTest(unittest.TestCase):
    def test_canonical_remote_lookup_ignores_all_git_rewrite_surfaces(self) -> None:
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        with tempfile.TemporaryDirectory() as directory:
            fake_git = Path(directory) / "git"
            fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            injected = {
                "PATH": directory,
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "url.file:///mirror.insteadOf",
                "GIT_CONFIG_VALUE_0": "https://github.com/",
                "GIT_DIR": "/tmp/untrusted.git",
                "GIT_EXEC_PATH": directory,
                "GIT_SSL_CAINFO": "/tmp/untrusted-ca.pem",
                "GIT_SSL_NO_VERIFY": "1",
                "GIT_WORK_TREE": "/tmp/untrusted-tree",
                "HTTPS_PROXY": "http://proxy.invalid",
                "https_proxy": "http://lower-proxy.invalid",
                "SSL_CERT_FILE": "/tmp/untrusted-cert.pem",
                "LD_PRELOAD": "/tmp/untrusted.so",
            }
            with mock.patch.dict(os.environ, injected, clear=False):
                with mock.patch.object(RECEIPT.subprocess, "run", return_value=completed) as run:
                    result = RECEIPT._run_canonical_remote("example/synthetic")
                    local_result = RECEIPT._run_git(ROOT, ["rev-parse", "HEAD"])
        self.assertIs(result, completed)
        self.assertIs(local_result, completed)
        remote_call, local_call = run.call_args_list
        argv = remote_call.args[0]
        options = remote_call.kwargs
        trusted_git = Path(argv[0])
        self.assertTrue(trusted_git.is_absolute())
        self.assertNotEqual(fake_git, trusted_git)
        self.assertEqual(
            [
                "ls-remote",
                "--symref",
                "--exit-code",
                "https://github.com/example/synthetic.git",
                "HEAD",
            ],
            argv[1:],
        )
        self.assertEqual(trusted_git, Path(local_call.args[0][0]))
        self.assertEqual(["rev-parse", "HEAD"], local_call.args[0][1:])
        self.assertEqual(Path("/"), options["cwd"])
        self.assertEqual("1", options["env"]["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual(os.devnull, options["env"]["GIT_CONFIG_GLOBAL"])
        self.assertEqual("0", options["env"]["GIT_CONFIG_COUNT"])
        self.assertNotIn("GIT_DIR", options["env"])
        self.assertNotIn("GIT_EXEC_PATH", options["env"])
        self.assertNotIn("GIT_SSL_CAINFO", options["env"])
        self.assertNotIn("GIT_SSL_NO_VERIFY", options["env"])
        self.assertNotIn("GIT_WORK_TREE", options["env"])
        self.assertNotIn("HTTPS_PROXY", options["env"])
        self.assertNotIn("https_proxy", options["env"])
        self.assertNotIn("SSL_CERT_FILE", options["env"])
        self.assertNotIn("LD_PRELOAD", options["env"])
        self.assertNotIn(directory, options["env"]["PATH"].split(os.pathsep))

    def test_canonical_ancestry_fetches_the_advertised_head_into_an_isolated_store(self) -> None:
        remote_head = "d" * 40
        candidate_head = "a" * 40
        completed = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, (remote_head + "\n").encode(), b""),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"", b""),
        ]
        with mock.patch.object(RECEIPT.subprocess, "run", side_effect=completed) as run:
            contained = RECEIPT._canonical_main_contains_head(
                "organvm/limen",
                "main",
                remote_head,
                candidate_head,
            )
        self.assertTrue(contained)
        calls = [call.args[0] for call in run.call_args_list]
        self.assertEqual("init", calls[0][1])
        self.assertIn("fetch", calls[1])
        self.assertIn("https://github.com/organvm/limen.git", calls[1])
        self.assertIn(f"{remote_head}:refs/canonical/main", calls[1])
        self.assertIn("rev-parse", calls[2])
        self.assertIn("cat-file", calls[3])
        self.assertIn("merge-base", calls[4])

    def test_predicate_runner_ignores_ambient_path_and_runtime_injection(self) -> None:
        self.assertNotIn(
            Path(sys.executable).resolve().parent,
            RECEIPT.TRUSTED_PREDICATE_EXECUTABLE_DIRECTORIES,
        )
        with tempfile.TemporaryDirectory() as directory:
            fake_python = Path(directory) / "python3"
            fake_python.write_text("#!/bin/sh\nprintf 'ambient fake\\n'\nexit 0\n", encoding="utf-8")
            fake_python.chmod(0o755)
            with mock.patch.dict(
                os.environ,
                {
                    "PATH": directory,
                    "PYTHONPATH": directory,
                    "NODE_OPTIONS": "--require=/tmp/untrusted.js",
                    "LD_PRELOAD": "/tmp/untrusted.so",
                    "LD_LIBRARY_PATH": directory,
                    "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
                },
                clear=False,
            ):
                prepared_argv, environment, metadata = RECEIPT._prepare_predicate_invocation(["python3", "-V"])
                with mock.patch.object(RECEIPT.platform, "system", return_value="Darwin"):
                    with mock.patch.object(
                        RECEIPT,
                        "_run_darwin_bounded_predicate",
                        return_value=(7, b"trusted executable\n", None),
                    ) as runner:
                        exit_code, output, failure = RECEIPT._run_bounded_predicate(
                            ["python3", "-c", "print('trusted executable'); raise SystemExit(7)"],
                            cwd=ROOT,
                            timeout_seconds=10,
                            max_output_bytes=4096,
                        )
        self.assertEqual((7, b"trusted executable\n", None), (exit_code, output, failure))
        self.assertNotEqual(str(fake_python), metadata["resolved_executable"])
        self.assertEqual(["-I", "-S"], prepared_argv[1:3])
        self.assertNotIn(directory, environment["PATH"].split(os.pathsep))
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("NODE_OPTIONS", environment)
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertNotIn("LD_LIBRARY_PATH", environment)
        self.assertNotIn("DYLD_INSERT_LIBRARIES", environment)
        invoked_argv = runner.call_args.args[0]
        invoked_environment = runner.call_args.kwargs["environment"]
        self.assertNotEqual(str(fake_python), invoked_argv[0])
        self.assertEqual(["-I", "-S"], invoked_argv[1:3])
        self.assertNotIn(directory, invoked_environment["PATH"].split(os.pathsep))
        self.assertNotIn("LD_PRELOAD", invoked_environment)
        self.assertNotIn("LD_LIBRARY_PATH", invoked_environment)
        self.assertNotIn("DYLD_INSERT_LIBRARIES", invoked_environment)

    def test_python_predicate_bootstrap_does_not_import_site(self) -> None:
        argv, environment, _metadata = RECEIPT._prepare_predicate_invocation(
            ["python3", "-c", "import sys; print('site' in sys.modules)"]
        )
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(b"False\n", completed.stdout)

    def test_user_managed_node_tool_requires_the_pinned_interpreter_and_cli_digests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            interpreter = root / "node"
            script = root / "npm-cli.js"
            interpreter.write_bytes(b"#!/bin/sh\nexit 0\n")
            interpreter.chmod(0o755)
            script.write_bytes(b"console.log('synthetic');\n")
            binding = {
                "interpreter": str(interpreter),
                "interpreter_sha256": RECEIPT.hashlib.sha256(interpreter.read_bytes()).hexdigest(),
                "script": str(script),
                "script_sha256": RECEIPT.hashlib.sha256(script.read_bytes()).hexdigest(),
            }
            identities = {(RECEIPT.platform.system(), RECEIPT.platform.machine()): {"npm": binding}}
            with mock.patch.object(RECEIPT, "PINNED_NODE_TOOL_CHAINS", identities):
                argv, _environment, metadata = RECEIPT._prepare_predicate_invocation(["npm", "test"])
                self.assertEqual([str(interpreter.resolve()), str(script.resolve()), "test"], argv)
                self.assertEqual(str(interpreter.resolve()), metadata["resolved_interpreter"])
                script.write_bytes(b"console.log('substituted');\n")
                with self.assertRaisesRegex(OSError, "differs from the pinned npm chain"):
                    RECEIPT._prepare_predicate_invocation(["npm", "test"])

    def test_darwin_supervisor_uses_isolated_python_and_a_sanitized_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private_root = Path(directory)
            injected = {
                "PYTHONPATH": directory,
                "PYTHONHOME": directory,
                "__PYVENV_LAUNCHER__": str(Path(directory) / "python"),
                "VIRTUAL_ENV": directory,
                "LD_PRELOAD": "/tmp/untrusted.so",
                "LD_LIBRARY_PATH": directory,
                "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
            }
            with mock.patch.dict(os.environ, injected, clear=False):
                argv, environment = RECEIPT._darwin_supervisor_invocation(
                    private_root / "status.json",
                    private_root / "environment.json",
                    private_root / "output.pipe",
                    private_root / "process.json",
                    private_root / "error.json",
                    ROOT,
                    [sys.executable, "-c", "print('predicate')"],
                )
        self.assertTrue(Path(argv[0]).is_absolute())
        self.assertEqual(["-I", "-S", "-c"], argv[1:4])
        self.assertIn(RECEIPT.DARWIN_SUPERVISOR, argv)
        self.assertIn('[sys.executable, "-I", "-S", "-c", paused_exec', RECEIPT.DARWIN_SUPERVISOR)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("PYTHONHOME", environment)
        self.assertNotIn("__PYVENV_LAUNCHER__", environment)
        self.assertNotIn("VIRTUAL_ENV", environment)
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertNotIn("LD_LIBRARY_PATH", environment)
        self.assertNotIn("DYLD_INSERT_LIBRARIES", environment)

    def test_authenticated_cost_transport_ignores_ambient_proxy_and_ca_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "trusted-ca.pem"
            bundle.write_text("test trust bundle", encoding="utf-8")
            context = mock.MagicMock()
            opener = mock.MagicMock()
            expected = object()
            opener.open.return_value = expected
            with mock.patch.object(COST, "CONTRACT_CA_BUNDLE_CANDIDATES", (bundle,)):
                with mock.patch.object(COST.ssl, "SSLContext", return_value=context):
                    with mock.patch.object(COST, "build_opener", return_value=opener) as build:
                        with mock.patch.dict(
                            os.environ,
                            {
                                "HTTPS_PROXY": "http://proxy.invalid",
                                "SSL_CERT_FILE": "/tmp/untrusted-cert.pem",
                            },
                            clear=False,
                        ):
                            result = COST._contract_https_open(COST.Request("https://api.github.com"), timeout=30)
        self.assertIs(expected, result)
        context.load_verify_locations.assert_called_once_with(cafile=str(bundle))
        handlers = build.call_args.args
        proxy = next(handler for handler in handlers if isinstance(handler, COST.ProxyHandler))
        https = next(handler for handler in handlers if isinstance(handler, COST.HTTPSHandler))
        self.assertEqual({}, proxy.proxies)
        self.assertIs(context, https._context)
        opener.open.assert_called_once_with(mock.ANY, timeout=30)

    def test_cost_failure_fixture_reproduces_all_dimensions(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        result = reproduce_cost(payload)
        self.assertEqual("withheld", result["status"])
        self.assertFalse(result["publication_eligible"])
        self.assertEqual(COST_INPUT_ARTIFACT, result["reproduction_command"]["input_artifact"])
        self.assertIsNone(result["review_verdict"])
        self.assertEqual(3, result["denominator"])
        self.assertEqual(3, result["population"]["population_count"])
        self.assertEqual(COST._canonical_digest(payload["population"]), result["population_digest"])
        self.assertEqual(1, result["terminal_states"]["failed"])
        self.assertEqual(1, result["terminal_states"]["failed_blocked"])
        self.assertEqual(5, len(result["dimensions"]))
        self.assertEqual(64, len(result["data_digest"]))

    def test_public_safe_observed_cost_sample_can_be_regenerated(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        payload["population"]["source_manifest"]["provenance"] = "public_safe_observed"
        payload["population"]["source_receipt_url"] = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
        payload["population"]["source_receipt_sha256"] = "b" * 64
        for row in payload["rows"]:
            row["model_cost_basis"] = "actual"
            row.pop("model_cost_rate_basis")
        with tempfile.TemporaryDirectory() as directory:
            population_artifact = Path(directory) / "population.json"
            input_artifact = Path(directory) / "input.json"
            review_artifact = Path(directory) / "review.json"
            population_raw = json.dumps(
                payload["population"]["source_manifest"], sort_keys=True, separators=(",", ":")
            ).encode()
            population_artifact.write_bytes(population_raw)
            payload["population"]["source_sha256"] = COST.hashlib.sha256(population_raw).hexdigest()
            review = independent_cost_review(payload)
            review["authority_receipt_url"] = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
            review["authority_receipt_sha256"] = "a" * 64
            input_artifact.write_text(json.dumps(payload), encoding="utf-8")
            review_artifact.write_text(json.dumps(review), encoding="utf-8")
            tracked = {
                payload["population"]["source_artifact"]: population_artifact,
                COST_INPUT_ARTIFACT: input_artifact,
                COST_REVIEW_ARTIFACT: review_artifact,
            }
            with mock.patch.object(COST, "_safe_tracked_artifact", side_effect=tracked.get):
                with mock.patch.object(
                    COST,
                    "_verify_authority_receipt",
                    side_effect=lambda *_args, **kwargs: (
                        ("chatgpt-codex-connector", "NONE")
                        if kwargs["evidence_kind"] == "independent_review"
                        else ("4444J99", "MEMBER")
                    ),
                ):
                    result = COST.reproduce(
                        payload,
                        input_artifact=COST_INPUT_ARTIFACT,
                        review_artifact=COST_REVIEW_ARTIFACT,
                        review_verdict=review,
                        **exact_cost_kwargs(payload, review),
                    )
        self.assertEqual("regenerated", result["status"])
        self.assertTrue(result["publication_eligible"])
        self.assertEqual("publishable_public_safe", result["review_verdict"]["verdict"])
        command = result["reproduction_command"]
        self.assertEqual(result["data_digest"], command["input_sha256"])
        self.assertEqual(COST._canonical_digest(result["review_verdict"]), command["review_sha256"])
        self.assertEqual(
            [
                "python3",
                "scripts/positioning-cost-failure-reproduction.py",
                "--source-repository",
                COST.CANONICAL_REPOSITORY,
                "--source-head",
                COST_SOURCE_HEAD,
                "--runner-blob",
                COST_RUNNER_BLOB,
                "--input",
                COST_INPUT_ARTIFACT,
                "--input-blob",
                COST_INPUT_BLOB,
                "--review",
                COST_REVIEW_ARTIFACT,
                "--review-blob",
                COST_REVIEW_BLOB,
            ],
            command["argv"],
        )
        self.assertEqual(COST_SOURCE_HEAD, command["source_head"])
        self.assertEqual(COST_RUNNER_BLOB, command["runner_blob"])
        self.assertEqual(COST_INPUT_BLOB, command["input_blob"])
        self.assertEqual(COST_REVIEW_BLOB, command["review_blob"])

    def test_public_safe_observed_cost_artifacts_reject_private_and_credential_material(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        payload["population"]["source_manifest"]["provenance"] = "public_safe_observed"
        payload["population"]["source_receipt_url"] = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
        payload["population"]["source_receipt_sha256"] = "b" * 64
        payload["rows"][0]["sample_id"] = "private-reader@example.invalid"
        payload["population"]["source_manifest"]["records"][0]["sample_id"] = "private-reader@example.invalid"
        with mock.patch.object(COST, "_verify_authority_receipt", return_value=("4444J99", "MEMBER")):
            errors = COST.validate_sample(payload)
        self.assertTrue(
            any("sample contains private or credential material" in error for error in errors),
            errors,
        )

        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        payload["population"]["source_manifest"]["provenance"] = "public_safe_observed"
        payload["population"]["source_receipt_url"] = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
        payload["population"]["source_receipt_sha256"] = "b" * 64
        for row in payload["rows"]:
            row["model_cost_basis"] = "actual"
            row.pop("model_cost_rate_basis")
        with tempfile.TemporaryDirectory() as directory:
            population_artifact = Path(directory) / "population.json"
            input_artifact = Path(directory) / "input.json"
            review_artifact = Path(directory) / "review.json"
            population_raw = json.dumps(
                payload["population"]["source_manifest"], sort_keys=True, separators=(",", ":")
            ).encode()
            population_artifact.write_bytes(population_raw)
            payload["population"]["source_sha256"] = COST.hashlib.sha256(population_raw).hexdigest()
            review = independent_cost_review(payload)
            review["limitations"] = [
                {
                    "note": "Nested credential-shaped metadata must fail closed.",
                    "api_token": "ghp_123456789012345678901234567890",
                }
            ]
            review["authority_receipt_url"] = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
            review["authority_receipt_sha256"] = "a" * 64
            input_artifact.write_text(json.dumps(payload), encoding="utf-8")
            review_artifact.write_text(json.dumps(review), encoding="utf-8")
            tracked = {
                payload["population"]["source_artifact"]: population_artifact,
                COST_INPUT_ARTIFACT: input_artifact,
                COST_REVIEW_ARTIFACT: review_artifact,
            }
            with (
                mock.patch.object(COST, "_safe_tracked_artifact", side_effect=tracked.get),
                mock.patch.object(COST, "_verify_authority_receipt", return_value=("4444J99", "MEMBER")),
            ):
                result = COST.reproduce(
                    payload,
                    input_artifact=COST_INPUT_ARTIFACT,
                    review_artifact=COST_REVIEW_ARTIFACT,
                    review_verdict=review,
                    **exact_cost_kwargs(payload, review),
                )
        self.assertEqual("withheld", result["status"])
        self.assertFalse(result["publication_eligible"])
        self.assertTrue(
            any("review contains private or credential material" in error for error in result["errors"]),
            result["errors"],
        )

    def test_synthetic_cost_artifacts_are_privacy_scanned_and_redacted_before_return(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        private_identity = "customer@example.invalid"
        private_limitation = "The password is hunter2alpha."
        payload["population"]["source_manifest"]["records"][0]["author_identity"] = private_identity
        review = independent_cost_review(payload)
        review["limitations"] = [private_limitation]
        result = COST.reproduce(
            payload,
            input_artifact=COST_INPUT_ARTIFACT,
            review_artifact=COST_REVIEW_ARTIFACT,
            review_verdict=review,
            **exact_cost_kwargs(payload, review),
        )
        serialized = json.dumps(result, sort_keys=True)
        self.assertEqual("withheld", result["status"])
        self.assertIsNone(result["population"])
        self.assertIsNone(result["review_verdict"])
        self.assertNotIn(private_identity, serialized)
        self.assertNotIn(private_limitation, serialized)

    def test_public_safe_scan_checks_identifier_values_inside_lists(self) -> None:
        findings = COST._find_forbidden_public_material({"record_id": ["private-123"]})
        self.assertEqual({"$.record_id[0]"}, findings)

    def test_public_safe_scan_rejects_natural_language_credential_assignments(self) -> None:
        for value in (
            "The API key is hunter2alpha",
            "The API key is: hunter2alpha",
            'The API key is "hunter2alpha".',
            "The password is correct-horse-battery-staple",
            "The password was hunter2alpha",
            "token is hunter2alpha",
            "credential: hunter2alpha",
            "passphrase was hunter2alpha",
        ):
            with self.subTest(value=value):
                findings = COST._find_forbidden_public_material({"limitations": [value]})
                self.assertEqual({"$.limitations[0]"}, findings)
        for value in (
            "The API key is not collected.",
            'The API key is "not collected".',
            "token is required",
            "token budget is bounded",
        ):
            with self.subTest(value=value):
                self.assertEqual(set(), COST._find_forbidden_public_material({"limitations": [value]}))

    def test_public_safe_scan_decodes_credential_url_parameter_names(self) -> None:
        forbidden_key = "api" + "_key"
        deeply_nested = f"https://target.example/proof?{forbidden_key}=plainvalue"
        for index in range(COST.PUBLIC_URL_NESTING_LIMIT + 2):
            deeply_nested = f"https://redirect-{index}.example/proof?next={quote(deeply_nested, safe='')}"
        for value in (
            "https://example.com/proof?api%5Fkey=plainvalue",
            "See https://example.com/proof#access%2Dtoken=plainvalue for the replay.",
            "https://example.com/proof?apiKey=",
            "https://user:password@example.com/proof",
            "https://example.com/proof?next=https%3A%2F%2Fother.example%2Fproof%3Fapi_key%3Dplainvalue",
            deeply_nested,
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    {"$.limitations[0]"},
                    COST._find_forbidden_public_material({"limitations": [value]}),
                )
        self.assertEqual(
            set(),
            COST._find_forbidden_public_material({"limitations": ["https://example.com/proof?claim_id=CLM-1"]}),
        )
        self.assertEqual(
            set(),
            COST._find_forbidden_public_material({"limitations": ["https://example.com/proof?next=bounded%252Dproof"]}),
        )

    def test_cost_failure_population_contract_prevents_cherry_picked_denominators(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        mutations = (
            ("selected_count", 1, "selected_count must equal"),
            ("population_count", 4, "population_count must equal"),
            ("eligible_count", True, "eligible_count must be"),
            ("selection_method", "manual_best_case", "selection_method"),
            ("selection_seed_sha256", "0" * 64, "census selection must not"),
            ("exclusion_counts", {"unreviewed": 1}, "exclusions must reconcile"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(payload)
                changed["population"][field] = value
                result = reproduce_cost(changed, reviewed=True)
                self.assertEqual("withheld", result["status"])
                self.assertTrue(any(expected in error for error in result["errors"]), result["errors"])

    def test_cost_failure_census_preserves_reconciled_ineligible_population_records(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        population = payload["population"]
        excluded = population["source_manifest"]["records"][-1]
        excluded["eligible"] = False
        excluded["exclusion_reason"] = "outside_observation_scope"
        excluded_id = excluded["sample_id"]
        payload["rows"] = [row for row in payload["rows"] if row["sample_id"] != excluded_id]
        population["population_count"] = 3
        population["eligible_count"] = 2
        population["selected_count"] = 2
        population["exclusion_counts"] = {"outside_observation_scope": 1}
        with tempfile.TemporaryDirectory() as directory:
            source_artifact = Path(directory) / "population.json"
            source_raw = json.dumps(population["source_manifest"], sort_keys=True, separators=(",", ":")).encode()
            source_artifact.write_bytes(source_raw)
            population["source_sha256"] = COST.hashlib.sha256(source_raw).hexdigest()
            original = COST._safe_tracked_artifact

            def tracked(value: object) -> Path | None:
                if value == population["source_artifact"]:
                    return source_artifact
                return original(value)

            with mock.patch.object(COST, "_safe_tracked_artifact", side_effect=tracked):
                errors = COST.validate_sample(payload)
        self.assertEqual([], errors)

    def test_cost_failure_population_manifest_and_hash_selection_are_reproduced(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        population = payload["population"]
        population["selection_method"] = "deterministic_hash_sample"
        population["selection_rule"] = COST.SELECTION_RULES["deterministic_hash_sample"]
        seed = COST._derived_selection_seed(population)
        population["selection_seed_sha256"] = seed
        eligible_ids = [record["sample_id"] for record in population["source_manifest"]["records"]]
        expected_ids = sorted(
            eligible_ids,
            key=lambda sample_id: (COST.hashlib.sha256(f"{seed}:{sample_id}".encode()).hexdigest(), sample_id),
        )
        rows_by_id = {row["sample_id"]: row for row in payload["rows"]}
        payload["rows"] = [rows_by_id[sample_id] for sample_id in expected_ids]
        self.assertEqual([], COST.validate_sample(payload))
        payload["rows"].reverse()
        errors = COST.validate_sample(payload)
        self.assertTrue(any("contract-owned hash selection" in error for error in errors), errors)

        payload["rows"].reverse()
        payload["population"]["selection_seed_sha256"] = "c" * 64
        errors = COST.validate_sample(payload)
        self.assertTrue(any("derive from immutable source and window" in error for error in errors), errors)

        payload["population"]["selection_seed_sha256"] = seed
        original_seed = COST._derived_selection_seed(payload["population"])
        payload["population"]["source_manifest"]["records"].reverse()
        self.assertEqual(original_seed, COST._derived_selection_seed(payload["population"]))
        payload["population"]["source_receipt_sha256"] = "f" * 64
        self.assertEqual(original_seed, COST._derived_selection_seed(payload["population"]))
        payload["population"]["source_manifest"]["records"][0]["sample_id"] = "changed-selection-identity"
        self.assertNotEqual(original_seed, COST._derived_selection_seed(payload["population"]))
        payload["population"]["source_manifest"]["records"][0]["sample_id"] = expected_ids[-1]
        payload["population"]["window_end"] = "2026-08-06"
        self.assertNotEqual(original_seed, COST._derived_selection_seed(payload["population"]))

        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["population"]["source_manifest"]["records"][0]["sample_id"] = "unbound-id"
        errors = COST.validate_sample(payload)
        self.assertTrue(any("tracked authoritative artifact" in error for error in errors), errors)

    def test_estimated_model_cost_requires_a_reproducible_rate_basis(self) -> None:
        for mutation, expected in (
            (("remove", None), "exact public-safe rate basis"),
            (("formula", "model_cost_usd = arbitrary"), "contract-owned formula"),
            (("calculated_cost_usd", 9.9), "exact formula"),
            (("model_id", "unbound-model"), "model_id differs from its tracked source record"),
            (("model_tier", "unbound-tier"), "model_tier differs from its tracked source record"),
            (("source_sha256", "0" * 64), "source SHA-256 differs from its tracked artifact"),
            (("source_artifact", "../../private-rate.json"), "safe tracked rate artifact"),
        ):
            with self.subTest(mutation=mutation):
                payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
                field, value = mutation
                if field == "remove":
                    payload["rows"][0].pop("model_cost_rate_basis")
                else:
                    payload["rows"][0]["model_cost_rate_basis"][field] = value
                errors = COST.validate_sample(payload)
                self.assertTrue(any(expected in error for error in errors), errors)

        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        errors = COST.validate_sample(payload)
        self.assertTrue(any("model rate source provenance" in error for error in errors), errors)

    def test_cost_artifacts_must_match_committed_head_bytes(self) -> None:
        artifact = "scripts/tests/fixtures/positioning-proof/synthetic-cost-failure.json"
        drifted = subprocess.CompletedProcess(["git", "show"], 0, b"drifted-worktree-bytes", b"")
        with tempfile.TemporaryDirectory() as directory:
            fake_git = Path(directory) / "git"
            fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_git.chmod(0o755)
            injected = {
                "PATH": directory,
                "GIT_EXEC_PATH": directory,
                "GIT_DIR": "/tmp/untrusted.git",
                "LD_PRELOAD": "/tmp/untrusted.so",
                "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
            }
            with (
                mock.patch.dict(COST.os.environ, injected, clear=False),
                mock.patch.object(COST.subprocess, "run", return_value=drifted) as run,
            ):
                self.assertIsNone(COST._safe_tracked_artifact(artifact))
        argv = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertTrue(Path(argv[0]).is_absolute())
        self.assertNotEqual(fake_git, Path(argv[0]))
        for key in injected:
            if key != "PATH":
                self.assertNotIn(key, environment)
        self.assertNotIn(directory, environment["PATH"].split(os.pathsep))

    def test_cost_authority_receipt_is_bound_to_an_authenticated_comment_actor(self) -> None:
        subject_sha256 = "c" * 64
        receipt = {
            "schema_version": COST.AUTHORITY_RECEIPT_SCHEMA,
            "evidence_kind": "population_manifest",
            "subject_sha256": subject_sha256,
            "actor_identity": "4444J99",
            "observed_at": "2026-08-08T12:00:00Z",
            "limitations": ["Hermetic authentication fixture only."],
        }
        receipt_sha256 = COST._canonical_digest(receipt)
        receipt_url = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
        comment = {
            "html_url": receipt_url,
            "user": {"login": "4444J99"},
            "author_association": "MEMBER",
            "body": "<!-- positioning-cost-authority-receipt -->\n```json\n" + json.dumps(receipt) + "\n```",
        }
        response = mock.MagicMock()
        response.read.return_value = json.dumps(comment).encode()
        response.__enter__.return_value = response
        with mock.patch.object(COST, "_contract_https_open", return_value=response):
            actor, association = COST._verify_authority_receipt(
                receipt_url,
                receipt_sha256,
                evidence_kind="population_manifest",
                subject_sha256=subject_sha256,
                require_trusted_association=True,
            )
        self.assertEqual(("4444J99", "MEMBER"), (actor, association))

        assignment_label = "".join(("pass", "word"))
        assignment_value = "".join(("hunter", "2"))
        for private_limitation in (
            "Contact customer@example.invalid for the private evidence set.",
            "Internal evidence is held under customer-123.",
            f"Replay {assignment_label}={assignment_value} in the private fixture.",
        ):
            receipt["limitations"] = [private_limitation]
            receipt_sha256 = COST._canonical_digest(receipt)
            comment["body"] = "<!-- positioning-cost-authority-receipt -->\n```json\n" + json.dumps(receipt) + "\n```"
            response.read.return_value = json.dumps(comment).encode()
            with self.subTest(private_limitation=private_limitation):
                with mock.patch.object(COST, "_contract_https_open", return_value=response):
                    with self.assertRaisesRegex(ValueError, "private or credential material"):
                        COST._verify_authority_receipt(
                            receipt_url,
                            receipt_sha256,
                            evidence_kind="population_manifest",
                            subject_sha256=subject_sha256,
                            require_trusted_association=True,
                        )
        receipt["limitations"] = ["Hermetic authentication fixture only."]

        receipt["evidence_kind"] = "independent_review"
        receipt_sha256 = COST._canonical_digest(receipt)
        comment.update(
            {
                "created_at": "2026-08-08T11:59:00Z",
                "updated_at": receipt["observed_at"],
                "body": "<!-- positioning-cost-authority-receipt -->\n```json\n" + json.dumps(receipt) + "\n```",
            }
        )
        response.read.return_value = json.dumps(comment).encode()
        with mock.patch.object(COST, "_contract_https_open", return_value=response):
            COST._verify_authority_receipt(
                receipt_url,
                receipt_sha256,
                evidence_kind="independent_review",
                subject_sha256=subject_sha256,
                expected_observed_at=receipt["observed_at"],
                authoritative_not_before=datetime.fromisoformat("2026-08-08T11:00:00+00:00"),
            )
        comment["updated_at"] = "2026-08-08T12:00:01Z"
        response.read.return_value = json.dumps(comment).encode()
        with mock.patch.object(COST, "_contract_https_open", return_value=response):
            with self.assertRaisesRegex(ValueError, "authenticated comment metadata"):
                COST._verify_authority_receipt(
                    receipt_url,
                    receipt_sha256,
                    evidence_kind="independent_review",
                    subject_sha256=subject_sha256,
                    expected_observed_at=receipt["observed_at"],
                    authoritative_not_before=datetime.fromisoformat("2026-08-08T11:00:00+00:00"),
                )

        receipt["observed_at"] = "2026-08-08T10:00:00Z"
        receipt_sha256 = COST._canonical_digest(receipt)
        comment.update(
            {
                "created_at": "2026-08-08T09:59:00Z",
                "updated_at": receipt["observed_at"],
                "body": "<!-- positioning-cost-authority-receipt -->\n```json\n" + json.dumps(receipt) + "\n```",
            }
        )
        response.read.return_value = json.dumps(comment).encode()
        with mock.patch.object(COST, "_contract_https_open", return_value=response):
            with self.assertRaisesRegex(ValueError, "predates the complete observation window"):
                COST._verify_authority_receipt(
                    receipt_url,
                    receipt_sha256,
                    evidence_kind="independent_review",
                    subject_sha256=subject_sha256,
                    expected_observed_at=receipt["observed_at"],
                    authoritative_not_before=datetime.fromisoformat("2026-08-08T11:00:00+00:00"),
                )

        comment["created_at"] = "2026-08-08T10:00:01Z"
        response.read.return_value = json.dumps(comment).encode()
        with mock.patch.object(COST, "_contract_https_open", return_value=response):
            with self.assertRaisesRegex(ValueError, "predates created_at"):
                COST._verify_authority_receipt(
                    receipt_url,
                    receipt_sha256,
                    evidence_kind="independent_review",
                    subject_sha256=subject_sha256,
                    expected_observed_at=receipt["observed_at"],
                    authoritative_not_before=datetime.fromisoformat("2026-08-08T09:00:00+00:00"),
                )

        receipt["evidence_kind"] = "population_manifest"
        receipt["observed_at"] = "2026-08-08T12:00:00Z"
        receipt_sha256 = COST._canonical_digest(receipt)
        comment["body"] = "<!-- positioning-cost-authority-receipt -->\n```json\n" + json.dumps(receipt) + "\n```"
        comment["author_association"] = "NONE"
        response.read.return_value = json.dumps(comment).encode()
        with mock.patch.object(COST, "_contract_https_open", return_value=response):
            with self.assertRaisesRegex(ValueError, "authorized repository actor"):
                COST._verify_authority_receipt(
                    receipt_url,
                    receipt_sha256,
                    evidence_kind="population_manifest",
                    subject_sha256=subject_sha256,
                    require_trusted_association=True,
                )

    def test_cost_authority_http_failures_are_structured_without_tracebacks(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        payload["population"]["source_manifest"]["provenance"] = "public_safe_observed"
        payload["population"]["source_receipt_url"] = "https://github.com/organvm/limen/issues/2200#issuecomment-1"
        payload["population"]["source_receipt_sha256"] = "a" * 64
        for row in payload["rows"]:
            row["model_cost_basis"] = "actual"
            row.pop("model_cost_rate_basis")
        with mock.patch.object(COST, "_verify_authority_receipt", side_effect=COST.HTTPException("partial")):
            errors = COST.validate_sample(payload)
        self.assertTrue(any("authority failed closed: partial" in error for error in errors), errors)

    def test_cost_failure_review_binds_population_and_cannot_be_future_dated(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        for field, value, expected in (
            ("population_digest", "0" * 64, "source population digest"),
            ("observed_at", "2099-01-01T00:00:00Z", "future"),
        ):
            review = independent_cost_review(payload)
            review[field] = value
            result = COST.reproduce(
                payload,
                input_artifact=COST_INPUT_ARTIFACT,
                review_artifact=COST_REVIEW_ARTIFACT,
                review_verdict=review,
            )
            self.assertEqual("withheld", result["status"])
            self.assertTrue(any(expected in error for error in result["errors"]), result["errors"])

        self_review = independent_cost_review(payload)
        self_review["reviewer_identity"] = payload["population"]["source_manifest"]["records"][0]["author_identity"]
        result = COST.reproduce(
            payload,
            input_artifact=COST_INPUT_ARTIFACT,
            review_artifact=COST_REVIEW_ARTIFACT,
            review_verdict=self_review,
        )
        self.assertTrue(any("differ from every sample author" in error for error in result["errors"]))

        case_variant = independent_cost_review(payload)
        case_variant["reviewer_identity"] = payload["population"]["source_manifest"]["records"][0][
            "author_identity"
        ].swapcase()
        result = COST.reproduce(
            payload,
            input_artifact=COST_INPUT_ARTIFACT,
            review_artifact=COST_REVIEW_ARTIFACT,
            review_verdict=case_variant,
        )
        self.assertTrue(any("differ from every sample author" in error for error in result["errors"]))

        spaced_identity = independent_cost_review(payload)
        spaced_identity["reviewer_identity"] = f" {spaced_identity['reviewer_identity']} "
        result = COST.reproduce(
            payload,
            input_artifact=COST_INPUT_ARTIFACT,
            review_artifact=COST_REVIEW_ARTIFACT,
            review_verdict=spaced_identity,
        )
        self.assertTrue(any("nonblank reviewer identity" in error for error in result["errors"]))

    def test_cost_failure_rejects_future_observations_and_predating_reviews(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        review = independent_cost_review(payload)
        review["observed_at"] = "2026-08-04T00:00:00Z"
        result = COST.reproduce(
            payload,
            input_artifact=COST_INPUT_ARTIFACT,
            review_artifact=COST_REVIEW_ARTIFACT,
            review_verdict=review,
        )
        self.assertTrue(any("follow the complete observation window" in error for error in result["errors"]))

        payload["window_end"] = "2099-01-01"
        payload["population"]["window_end"] = "2099-01-01"
        payload["population"]["source_manifest"]["window_end"] = "2099-01-01"
        payload["rows"][0]["observed_at"] = "2099-01-01T00:00:00Z"
        errors = COST.validate_sample(payload)
        self.assertTrue(any("cannot end in the future" in error for error in errors), errors)
        self.assertTrue(any("cannot be in the future" in error for error in errors), errors)

    def test_cost_failure_retry_count_requires_a_nonnegative_integer(self) -> None:
        for value in (0.5, True, -1):
            payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
            payload["rows"][0]["retry_count"] = value
            result = reproduce_cost(payload)
            self.assertEqual("withheld", result["status"])
            self.assertTrue(any("non-negative integer" in error for error in result["errors"]))

    def test_cost_failure_cli_reports_unreadable_or_malformed_inputs_without_tracebacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_input = root / "sample.json"
            valid_input.write_text(
                (FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            malformed = root / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            missing = root / "missing.json"
            for argv in (
                [
                    sys.executable,
                    str(ROOT / "scripts/positioning-cost-failure-reproduction.py"),
                    "--input",
                    str(malformed),
                ],
                [
                    sys.executable,
                    str(ROOT / "scripts/positioning-cost-failure-reproduction.py"),
                    "--input",
                    str(missing),
                ],
                [
                    sys.executable,
                    str(ROOT / "scripts/positioning-cost-failure-reproduction.py"),
                    "--input",
                    str(valid_input),
                    "--review",
                    str(malformed),
                ],
            ):
                completed = subprocess.run(argv, cwd=ROOT, check=False, capture_output=True, text=True)
                self.assertEqual(1, completed.returncode)
                self.assertEqual("", completed.stderr)
                result = json.loads(completed.stdout)
                self.assertEqual("withheld", result["status"])
                self.assertFalse(result["publication_eligible"])
                self.assertTrue(any("failed closed" in error for error in result["errors"]))

    def test_cost_failure_required_receipt_fields_fail_closed_before_publication(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["provenance"] = "public_safe_observed"
        valid = reproduce_cost(payload, reviewed=True)
        circular_review = copy.deepcopy(valid["review_verdict"])
        circular_review["reviewer_class"] = "deterministic_contract_validator"
        drifted_review = copy.deepcopy(valid["review_verdict"])
        drifted_review["data_digest"] = "0" * 64
        mutations = (
            ("reproduction_command", None, "reproduction_command"),
            ("reproduction_command", ["python3", "unreviewed.py"], "reproduction_command"),
            ("review_verdict", None, "structured independent review_verdict"),
            ("review_verdict", {"status": "pass"}, "exact contract fields"),
            ("review_verdict", circular_review, "independent reviewer class"),
            ("review_verdict", drifted_review, "does not bind the analyzed data digest"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field, value=value):
                analysis = copy.deepcopy(valid)
                if value is None:
                    analysis.pop(field)
                else:
                    analysis[field] = value
                result = COST._finalize_analysis(analysis, data_complete=True)
                self.assertEqual("withheld", result["status"])
                self.assertFalse(result["publication_eligible"])
                self.assertTrue(any(expected_error in error for error in result["errors"]), result["errors"])

    def test_cost_failure_sample_ids_are_normalized_before_deduplication(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["rows"][1]["sample_id"] = f" {payload['rows'][0]['sample_id']} "
        result = reproduce_cost(payload)
        self.assertEqual("withheld", result["status"])
        self.assertTrue(any("unique public-safe sample_id" in error for error in result["errors"]))

    def test_cost_failure_requires_explicit_provenance(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        for provenance in (None, "synthetic_or_public_safe", {"mode": "synthetic"}):
            mutated = copy.deepcopy(payload)
            if provenance is None:
                mutated.pop("provenance")
            else:
                mutated["provenance"] = provenance
            result = reproduce_cost(mutated)
            self.assertEqual("withheld", result["status"])
            self.assertTrue(
                any("explicit synthetic or public_safe_observed provenance" in error for error in result["errors"])
            )

    def test_receipt_request_requires_a_typed_repository_path(self) -> None:
        for repository_path in (None, {"path": "/tmp/repository"}, ["/tmp/repository"]):
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": repository_path,
                "default_branch": "main",
                "expected_head": "a" * 40,
                "predicate": {
                    "argv": [sys.executable, "-c", "print('pass')"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            result = run_request(request)
            self.assertEqual("blocked_external", result["result"])
            self.assertTrue(any("nonblank path string" in error for error in result["errors"]))

    def test_receipt_request_rejects_malformed_public_fields_before_execution(self) -> None:
        mutations = (
            ("flagship_id", {"id": "synthetic"}, "flagship_id"),
            ("limitations", [{"note": "synthetic"}], "limitations"),
            ("limitations", [""], "limitations"),
            ("timeout_seconds", True, "timeout"),
            ("argv", [sys.executable, "bad\0argument"], "NUL-free"),
        )
        for field, value, expected_error in mutations:
            request = {
                "schema_version": RECEIPT.SCHEMA_VERSION,
                "flagship_id": "synthetic",
                "repository": "example/synthetic",
                "repository_path": "/tmp/synthetic",
                "default_branch": "main",
                "expected_head": "a" * 40,
                "predicate": {
                    "argv": [sys.executable, "-c", "print('pass')"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            target = request["predicate"] if field in {"timeout_seconds", "argv"} else request
            assert isinstance(target, dict)
            target[field] = value
            result = run_request(request)
            self.assertEqual("blocked_external", result["result"])
            self.assertTrue(any(expected_error in error for error in result["errors"]))

    def test_receipt_request_never_copies_unsafe_limitations_into_a_receipt(self) -> None:
        nested_credential_url = "https://target.example/proof?" + "api_" + "key=" + "plain" + "value"
        for index in range(4):
            nested_credential_url = (
                f"https://redirect-{index}.example/proof?next={quote(nested_credential_url, safe='')}"
            )
        unsafe_limitations = (
            "Contact customer@example.invalid for the evidence.",
            "The password is hunter2alpha.",
            "Private record customer-123 is excluded.",
            "https://example.com/proof?api%5Fkey=plainvalue",
            "See https://example.com/proof?api%5Fkey=plainvalue for proof.",
            "See https://example.com/proof?next=https%253A%252F%252Fexample.com%252F%253Faccess_token%253Dplainvalue.",
            f"See {nested_credential_url} for proof.",
            "See https://example.com/proof?next=%2F%2Ftarget.example%2F%3Fapi_key%3Dplainvalue for proof.",
        )
        for limitation in unsafe_limitations:
            with self.subTest(limitation=limitation):
                request = {
                    "schema_version": RECEIPT.SCHEMA_VERSION,
                    "flagship_id": "synthetic",
                    "repository": "example/synthetic",
                    "repository_path": "/tmp/synthetic",
                    "default_branch": "main",
                    "expected_head": "a" * 40,
                    "predicate": {
                        "argv": ["python3", "-c", "print('pass')"],
                        "timeout_seconds": 10,
                        "max_output_bytes": 4096,
                    },
                    "limitations": [limitation],
                }
                with mock.patch.object(
                    RECEIPT,
                    "_proof_contract_snapshot",
                    side_effect=AssertionError("unsafe limitations must fail before contract inspection"),
                ):
                    result = RECEIPT.run_request(request)
                self.assertEqual("blocked_external", result["result"])
                self.assertEqual([], result["limitations"])
                self.assertNotIn(limitation, json.dumps(result, sort_keys=True))

    def test_validation_error_receipts_do_not_copy_unsafe_request_fields(self) -> None:
        request = {
            "schema_version": RECEIPT.SCHEMA_VERSION,
            "flagship_id": "password is hunter2alpha",
            "repository": "example/synthetic",
            "repository_path": "/tmp/synthetic",
            "default_branch": "main",
            "expected_head": "a" * 40,
            "predicate": {
                "argv": ["python3", "-c", "print('pass')"],
                "timeout_seconds": 10,
                "max_output_bytes": 4096,
            },
            "limitations": ["Synthetic fixture only."],
            "api_key_hunter2alpha": "rejected",
        }
        with mock.patch.object(RECEIPT, "_proof_contract_snapshot", return_value=({}, {})):
            result = RECEIPT.run_request(request)
        serialized = json.dumps(result, sort_keys=True)
        self.assertEqual("blocked_external", result["result"])
        self.assertNotIn("hunter2alpha", serialized)
        self.assertNotIn("flagship_id", result)
        self.assertEqual(["Synthetic fixture only."], result["limitations"])

        secret_exception = "contract inspection failed: password is hunter2alpha"
        with mock.patch.object(RECEIPT, "_proof_contract_snapshot", side_effect=ValueError(secret_exception)):
            failed = RECEIPT.run_request({"limitations": ["Synthetic fixture only."]})
        failed_serialized = json.dumps(failed, sort_keys=True)
        self.assertNotIn("hunter2alpha", failed_serialized)
        self.assertNotIn(secret_exception, failed_serialized)

    def test_receipt_cli_emits_blocked_receipt_for_unreadable_or_malformed_request(self) -> None:
        cases = {
            "missing": None,
            "invalid-utf8": b"\xff\xfe",
            "malformed-json": b'{"schema_version":',
            "non-object": b"[]",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, payload in cases.items():
                with self.subTest(name=name):
                    request_path = root / f"{name}.json"
                    output_path = root / f"{name}-receipt.json"
                    if payload is not None:
                        request_path.write_bytes(payload)
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "scripts/positioning-flagship-receipt.py"),
                            "--request",
                            str(request_path),
                            "--output",
                            str(output_path),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(1, result.returncode)
                    self.assertEqual("", result.stderr)
                    receipt = json.loads(result.stdout)
                    self.assertEqual("limen.positioning_flagship_receipt.v1", receipt["schema_version"])
                    self.assertEqual("blocked_external", receipt["result"])
                    self.assertTrue(receipt["errors"])
                    self.assertEqual(result.stdout, output_path.read_text(encoding="utf-8"))

    def test_receipt_request_blocks_when_contract_git_inspection_times_out(self) -> None:
        timeout = subprocess.TimeoutExpired(["git", "show"], 60)
        with mock.patch.object(RECEIPT, "_proof_contract_snapshot", side_effect=timeout):
            result = RECEIPT.run_request({"limitations": ["Synthetic fixture only."]})
        self.assertEqual("blocked_external", result["result"])
        self.assertTrue(any("proof contract is unavailable" in error for error in result["errors"]))

    def test_receipt_request_binds_selected_flagships_to_contract_owned_predicates(self) -> None:
        payload = json.loads(RECEIPT.PROOF_CONTRACT.read_text(encoding="utf-8"))
        contract = RECEIPT._flagship_contract_from_payload(payload, "limen")
        assert contract is not None
        request = {
            "schema_version": RECEIPT.SCHEMA_VERSION,
            "flagship_id": "limen",
            "repository": contract["repository"],
            "repository_path": "/tmp/limen-flagship",
            "default_branch": contract["default_branch"],
            "expected_head": "a" * 40,
            "predicate": copy.deepcopy(contract["predicate"]),
            "limitations": ["Validation-only fixture."],
        }
        self.assertEqual([], RECEIPT.validate_request(request, contract_payload=payload))

        drifted = copy.deepcopy(request)
        drifted["predicate"]["argv"] = [sys.executable, "-c", "print('pass')"]
        errors = RECEIPT.validate_request(drifted, contract_payload=payload)
        self.assertTrue(any("contract-owned flagship command" in error for error in errors), errors)

        unknown = copy.deepcopy(request)
        unknown["flagship_id"] = "arbitrary"
        errors = RECEIPT.validate_request(unknown, contract_payload=payload)
        self.assertTrue(any("not selected by the proof contract" in error for error in errors), errors)

    def test_cost_failure_private_or_unknown_fields_fail_closed(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["rows"][0]["customer"] = "private"
        result = reproduce_cost(payload)
        self.assertEqual("withheld", result["status"])
        self.assertFalse(result["publication_eligible"])

    def test_cost_failure_public_artifacts_reject_duplicate_json_members(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON member: sample_id"):
            COST._loads_public_artifact('{"row":{"sample_id":"private","sample_id":"public"}}')

    def test_tracked_rate_and_population_artifacts_reject_duplicate_members(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "duplicate.json"

            rate_source = json.loads((FIXTURES / "synthetic-model-rate-source.json").read_text(encoding="utf-8"))
            rate_raw = json.dumps(rate_source, separators=(",", ":"))[:-1]
            rate_raw += f',"source_id":{json.dumps(rate_source["source_id"])}' + "}"
            artifact.write_text(rate_raw, encoding="utf-8")
            rate_basis = copy.deepcopy(payload["rows"][0]["model_cost_rate_basis"])
            rate_basis["source_sha256"] = COST.hashlib.sha256(rate_raw.encode()).hexdigest()
            rate_errors: list[str] = []
            with mock.patch.object(COST, "_safe_tracked_artifact", return_value=artifact):
                COST._model_rate_source_record(rate_basis, 0, rate_errors, "synthetic")
            self.assertTrue(any("duplicate JSON member: source_id" in error for error in rate_errors), rate_errors)

            population = copy.deepcopy(payload["population"])
            population_source = population["source_manifest"]
            population_raw = json.dumps(population_source, separators=(",", ":"))[:-1]
            population_raw += f',"source_id":{json.dumps(population_source["source_id"])}' + "}"
            artifact.write_text(population_raw, encoding="utf-8")
            population["source_sha256"] = COST.hashlib.sha256(population_raw.encode()).hexdigest()
            population_errors: list[str] = []
            with mock.patch.object(COST, "_safe_tracked_artifact", return_value=artifact):
                COST._validate_population_source(population, "synthetic", population_errors)
            self.assertTrue(
                any("duplicate JSON member: source_id" in error for error in population_errors),
                population_errors,
            )

    def test_cost_failure_reproduction_requires_committed_replay_artifacts(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        review = independent_cost_review(payload)
        untracked = COST.reproduce(
            payload,
            input_artifact="sample.json",
            review_artifact="review.json",
            review_verdict=review,
        )
        self.assertTrue(any("requires the exact input blob" in error for error in untracked["errors"]))
        self.assertTrue(any("requires the exact review blob" in error for error in untracked["errors"]))

        mutated = copy.deepcopy(payload)
        mutated["rows"][0]["human_minutes"] += 1
        drifted = COST.reproduce(
            mutated,
            input_artifact=COST_INPUT_ARTIFACT,
            **exact_cost_kwargs(payload),
        )
        self.assertTrue(any("input differs from its committed HEAD artifact" in error for error in drifted["errors"]))

    def test_cost_failure_auto_replay_head_must_exist_in_the_canonical_remote(self) -> None:
        review = {"verdict": "withheld"}
        identities = (
            (COST_SOURCE_HEAD, COST_RUNNER_BLOB),
            (COST_SOURCE_HEAD, COST_INPUT_BLOB),
            (COST_SOURCE_HEAD, COST_REVIEW_BLOB),
        )
        with (
            mock.patch.object(COST, "_tracked_artifact_identity", side_effect=identities),
            mock.patch.object(
                COST,
                "_fetch_exact_replay_artifacts",
                side_effect=ValueError("canonical replay head could not be fetched"),
            ) as fetch,
        ):
            rejected = COST._build_reproduction_command(
                COST_INPUT_ARTIFACT,
                "a" * 64,
                COST_REVIEW_ARTIFACT,
                review,
            )
        self.assertIsNone(rejected["source_head"])
        fetch.assert_called_once_with(
            COST_SOURCE_HEAD,
            COST_RUNNER_BLOB,
            {
                COST_INPUT_ARTIFACT: COST_INPUT_BLOB,
                COST_REVIEW_ARTIFACT: COST_REVIEW_BLOB,
            },
        )

        with (
            mock.patch.object(COST, "_tracked_artifact_identity", side_effect=identities),
            mock.patch.object(COST, "_fetch_exact_replay_artifacts", return_value={}),
        ):
            accepted = COST._build_reproduction_command(
                COST_INPUT_ARTIFACT,
                "a" * 64,
                COST_REVIEW_ARTIFACT,
                review,
            )
        self.assertEqual(COST_SOURCE_HEAD, accepted["source_head"])

        with (
            mock.patch.object(COST, "_tracked_artifact_identity", side_effect=identities),
            mock.patch.object(
                COST,
                "_fetch_exact_replay_artifacts",
                side_effect=subprocess.TimeoutExpired(["git", "fetch"], 120),
            ),
        ):
            timed_out = COST._build_reproduction_command(
                COST_INPUT_ARTIFACT,
                "a" * 64,
                COST_REVIEW_ARTIFACT,
                review,
            )
        self.assertIsNone(timed_out["source_head"])

    def test_cost_failure_exact_replay_timeout_is_structured_and_withheld(self) -> None:
        argv = [
            "positioning-cost-failure-reproduction.py",
            "--source-repository",
            COST.CANONICAL_REPOSITORY,
            "--source-head",
            COST_SOURCE_HEAD,
            "--runner-blob",
            COST_RUNNER_BLOB,
            "--input",
            COST_INPUT_ARTIFACT,
            "--input-blob",
            COST_INPUT_BLOB,
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(
                COST,
                "_fetch_exact_replay_artifacts",
                side_effect=subprocess.TimeoutExpired(["git", "fetch"], 120),
            ),
            mock.patch("builtins.print") as emit,
        ):
            exit_code = COST.main()
        self.assertEqual(1, exit_code)
        result = json.loads(emit.call_args.args[0])
        self.assertEqual("withheld", result["status"])
        self.assertTrue(any("timed out" in error for error in result["errors"]))

    def test_cost_failure_exact_replay_fetches_and_reads_only_the_recorded_head_and_blobs(self) -> None:
        population_path = "scripts/tests/fixtures/positioning-proof/exact-population.json"
        rate_path = "scripts/tests/fixtures/positioning-proof/exact-rates.json"
        payload = {
            "schema_version": COST.SCHEMA_VERSION,
            "population": {"source_artifact": population_path},
            "rows": [{"model_cost_rate_basis": {"source_artifact": rate_path}}],
        }
        review = {"schema_version": "synthetic.review.v1", "verdict": "withheld"}
        population_source = {"schema_version": "synthetic.population.v1"}
        rate_source = {"schema_version": "synthetic.rates.v1"}
        input_raw = json.dumps(payload).encode()
        review_raw = json.dumps(review).encode()
        population_raw = json.dumps(population_source).encode()
        rate_raw = json.dumps(rate_source).encode()
        default_head = "f" * 40
        git_outputs = (
            (default_head + "\n").encode(),
            b"",
            b"",
            (COST_RUNNER_BLOB + "\n").encode(),
            Path(COST.__file__).resolve().read_bytes(),
            (COST_INPUT_BLOB + "\n").encode(),
            input_raw,
            (COST_REVIEW_BLOB + "\n").encode(),
            review_raw,
            ("1" * 40 + "\n").encode(),
            population_raw,
            ("2" * 40 + "\n").encode(),
            rate_raw,
        )
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        with (
            mock.patch.object(COST, "_canonical_remote_default_head", return_value=("main", default_head)),
            mock.patch.object(COST.subprocess, "run", side_effect=(completed,) * 5) as run,
            mock.patch.object(COST, "_git_output", side_effect=git_outputs) as git_output,
        ):
            observed = COST._fetch_exact_replay_artifacts(
                COST_SOURCE_HEAD,
                COST_RUNNER_BLOB,
                {
                    COST_INPUT_ARTIFACT: COST_INPUT_BLOB,
                    COST_REVIEW_ARTIFACT: COST_REVIEW_BLOB,
                },
            )
        self.assertEqual(payload, observed[COST_INPUT_ARTIFACT])
        self.assertEqual(review, observed[COST_REVIEW_ARTIFACT])
        self.assertEqual(population_source, observed[population_path])
        self.assertEqual(rate_source, observed[rate_path])
        fetch = run.call_args_list[4].args[0]
        self.assertIn("--filter=blob:none", fetch)
        self.assertNotIn("--depth=1", fetch)
        self.assertIn(f"{default_head}:refs/canonical/main", fetch)
        self.assertIn(f"{COST_SOURCE_HEAD}:{COST.RUNNER_ARTIFACT}", git_output.call_args_list[3].args[0])
        self.assertIn(f"{COST_SOURCE_HEAD}:{COST_INPUT_ARTIFACT}", git_output.call_args_list[5].args[0])
        self.assertIn(f"{COST_SOURCE_HEAD}:{COST_REVIEW_ARTIFACT}", git_output.call_args_list[7].args[0])
        self.assertIn(f"{COST_SOURCE_HEAD}:{population_path}", git_output.call_args_list[9].args[0])
        self.assertIn(f"{COST_SOURCE_HEAD}:{rate_path}", git_output.call_args_list[11].args[0])
        for call in git_output.call_args_list:
            self.assertIsNotNone(call.kwargs.get("git_dir"))

        wrong_blob_outputs = (
            (default_head + "\n").encode(),
            b"",
            b"",
            ("e" * 40 + "\n").encode(),
        )
        with (
            mock.patch.object(COST, "_canonical_remote_default_head", return_value=("main", default_head)),
            mock.patch.object(COST.subprocess, "run", side_effect=(completed,) * 5),
            mock.patch.object(COST, "_git_output", side_effect=wrong_blob_outputs),
            self.assertRaisesRegex(ValueError, "runner blob differs"),
        ):
            COST._fetch_exact_replay_artifacts(
                COST_SOURCE_HEAD,
                COST_RUNNER_BLOB,
                {COST_INPUT_ARTIFACT: COST_INPUT_BLOB},
            )

        with (
            mock.patch.object(COST, "_canonical_remote_default_head", return_value=("main", default_head)),
            mock.patch.object(COST.subprocess, "run", side_effect=(completed,) * 5),
            mock.patch.object(
                COST,
                "_git_output",
                side_effect=((default_head + "\n").encode(), b"", ValueError("not an ancestor")),
            ),
            self.assertRaisesRegex(ValueError, "not contained in canonical main"),
        ):
            COST._fetch_exact_replay_artifacts(
                COST_SOURCE_HEAD,
                COST_RUNNER_BLOB,
                {COST_INPUT_ARTIFACT: COST_INPUT_BLOB},
            )

    def test_cost_failure_identities_reject_unicode_format_controls(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        payload["population"]["source_manifest"]["records"][0]["author_identity"] += "\u200b"
        errors = COST.validate_sample(payload)
        self.assertTrue(any("public-safe author identity" in error for error in errors), errors)

        clean = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        review = independent_cost_review(clean)
        review["reviewer_identity"] += "\u200b"
        result = COST.reproduce(
            clean,
            input_artifact=COST_INPUT_ARTIFACT,
            review_artifact=COST_REVIEW_ARTIFACT,
            review_verdict=review,
        )
        self.assertTrue(any("canonical authenticated character set" in error for error in result["errors"]))

    def test_exact_replay_validates_nested_sources_from_the_recorded_bundle_only(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        paths = {
            payload["population"]["source_artifact"],
            *(row["model_cost_rate_basis"]["source_artifact"] for row in payload["rows"]),
        }
        bundle = COST.ExactReplayArtifacts()
        for path in paths:
            raw = (ROOT / path).read_bytes()
            bundle[path] = COST._loads_public_artifact(raw.decode("utf-8"))
            bundle.raw_by_path[path] = raw
            bundle.blob_by_path[path] = "a" * 40
        with mock.patch.object(COST, "_safe_tracked_artifact", side_effect=AssertionError("local fallback")):
            self.assertEqual([], COST.validate_sample(payload, exact_artifacts=bundle))

        population_path = payload["population"]["source_artifact"]
        bundle.raw_by_path[population_path] += b"\n"
        errors = COST.validate_sample(payload, exact_artifacts=bundle)
        self.assertTrue(any("source SHA-256 differs" in error for error in errors), errors)

    def test_cost_failure_oversized_numbers_fail_closed_without_overflow(self) -> None:
        cases = (
            ("model_cost_usd", None),
            ("retry_count", None),
            ("input_units", "model_cost_rate_basis"),
            ("input_rate_usd_per_million", "model_cost_rate_basis"),
        )
        for field, parent in cases:
            with self.subTest(field=field):
                payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
                target = payload["rows"][0] if parent is None else payload["rows"][0][parent]
                target[field] = 10**1000
                result = reproduce_cost(payload)
                self.assertEqual("withheld", result["status"])
                self.assertTrue(any(field in error for error in result["errors"]), result["errors"])

    def test_cost_failure_unhashable_failure_classes_fail_closed(self) -> None:
        for failure_class in ({"code": "timeout"}, ["timeout"]):
            payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
            payload["rows"][1]["failure_class"] = failure_class
            result = reproduce_cost(payload)
            self.assertEqual("withheld", result["status"])
            self.assertTrue(any("reviewed public failure_class" in error for error in result["errors"]))

    def test_cost_failure_unhashable_review_enums_fail_closed(self) -> None:
        for field, value, expected in (
            ("reviewer_class", {"class": "independent_model"}, "independent reviewer class"),
            ("verdict", ["publishable_public_safe"], "explicitly publish or withhold"),
        ):
            with self.subTest(field=field):
                payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
                review = independent_cost_review(payload)
                review[field] = value
                result = COST.reproduce(
                    payload,
                    input_artifact=COST_INPUT_ARTIFACT,
                    review_artifact=COST_REVIEW_ARTIFACT,
                    review_verdict=review,
                )
                self.assertEqual("withheld", result["status"])
                self.assertTrue(any(expected in error for error in result["errors"]), result["errors"])

    def test_cost_failure_unhashable_identity_and_state_fields_fail_closed(self) -> None:
        cases = (
            ("sample_id", {"id": "synthetic"}, "sample_id"),
            ("sample_id", ["synthetic"], "sample_id"),
            ("terminal_state", {"state": "failed"}, "terminal_state"),
            ("terminal_state", ["failed"], "terminal_state"),
            ("model_cost_basis", {"basis": "actual"}, "model_cost_basis"),
            ("model_cost_basis", ["actual"], "model_cost_basis"),
        )
        for field, value, expected_error in cases:
            payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
            payload["rows"][1][field] = value
            result = reproduce_cost(payload)
            self.assertEqual("withheld", result["status"])
            self.assertTrue(any(expected_error in error for error in result["errors"]))

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
        result = reproduce_cost(payload)
        self.assertEqual("withheld", result["status"])
        self.assertTrue(any("reviewed public failure_class" in error for error in result["errors"]))
        self.assertTrue(any("positive measured cost/time" in error for error in result["errors"]))

    def test_non_done_explicit_unknown_withholds_publication(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        failed = payload["rows"][1]
        failed["model_cost_usd"] = None
        failed["model_cost_basis"] = "unknown"
        failed["human_minutes"] = None
        result = reproduce_cost(payload)
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
            self.assertEqual("a" * 40, result["environment"]["proof_contract_head"])
            self.assertEqual("b" * 40, result["environment"]["proof_contract_blob"])
            self.assertEqual("c" * 64, result["environment"]["proof_contract_sha256"])

    def test_flagship_contract_must_match_the_committed_runner_blob(self) -> None:
        committed = json.dumps(
            {"exact_head_receipt_plan": {"flagship_predicates": {}}},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        completed = (
            subprocess.CompletedProcess([], 0, ("a" * 40 + "\n").encode(), b""),
            subprocess.CompletedProcess([], 0, ("b" * 40 + "\n").encode(), b""),
            subprocess.CompletedProcess([], 0, committed, b""),
            subprocess.CompletedProcess([], 0, b"", b""),
        )
        remote = subprocess.CompletedProcess(
            [],
            0,
            (f"ref: refs/heads/main\tHEAD\n{'a' * 40}\tHEAD\n").encode(),
            b"",
        )
        with tempfile.TemporaryDirectory() as directory:
            contract = Path(directory) / "contract.json"
            contract.write_bytes(committed)
            with (
                mock.patch.object(RECEIPT, "PROOF_CONTRACT", contract),
                mock.patch.object(RECEIPT, "_run_git", side_effect=completed),
                mock.patch.object(RECEIPT, "_run_canonical_remote", return_value=remote),
                mock.patch.object(RECEIPT, "_canonical_main_contains_head", return_value=True),
            ):
                payload, metadata = RECEIPT._proof_contract_snapshot()
            self.assertEqual({}, payload["exact_head_receipt_plan"]["flagship_predicates"])
            self.assertEqual("a" * 40, metadata["proof_contract_head"])
            self.assertEqual("b" * 40, metadata["proof_contract_blob"])
            self.assertEqual(RECEIPT.hashlib.sha256(committed).hexdigest(), metadata["proof_contract_sha256"])
            self.assertEqual("main", metadata["proof_contract_canonical_branch"])
            self.assertEqual("a" * 40, metadata["proof_contract_canonical_head"])

            contract.write_bytes(b'{"exact_head_receipt_plan":{"flagship_predicates":{"limen":{}}}}')
            with (
                mock.patch.object(RECEIPT, "PROOF_CONTRACT", contract),
                mock.patch.object(RECEIPT, "_run_git", side_effect=completed),
                mock.patch.object(RECEIPT, "_run_canonical_remote", return_value=remote),
                mock.patch.object(RECEIPT, "_canonical_main_contains_head", return_value=True),
                self.assertRaisesRegex(ValueError, "differ from the committed runner blob"),
            ):
                RECEIPT._proof_contract_snapshot()

            contract.write_bytes(committed)
            with (
                mock.patch.object(RECEIPT, "PROOF_CONTRACT", contract),
                mock.patch.object(RECEIPT, "_run_git", side_effect=completed),
                mock.patch.object(RECEIPT, "_run_canonical_remote", return_value=remote),
                mock.patch.object(RECEIPT, "_canonical_main_contains_head", return_value=False),
                self.assertRaisesRegex(ValueError, "not contained in canonical Limen main"),
            ):
                RECEIPT._proof_contract_snapshot()

            advanced_remote = subprocess.CompletedProcess(
                [],
                0,
                (f"ref: refs/heads/main\tHEAD\n{'d' * 40}\tHEAD\n").encode(),
                b"",
            )
            with (
                mock.patch.object(RECEIPT, "PROOF_CONTRACT", contract),
                mock.patch.object(RECEIPT, "_run_git", side_effect=completed),
                mock.patch.object(RECEIPT, "_run_canonical_remote", return_value=advanced_remote),
                mock.patch.object(RECEIPT, "_canonical_main_contains_head", return_value=True),
                self.assertRaisesRegex(ValueError, "not the latest canonical Limen main head"),
            ):
                RECEIPT._proof_contract_snapshot()

            unavailable_remote = subprocess.CompletedProcess([], 1, b"", b"canonical remote unavailable")
            with (
                mock.patch.object(RECEIPT, "PROOF_CONTRACT", contract),
                mock.patch.object(RECEIPT, "_run_git", side_effect=completed),
                mock.patch.object(RECEIPT, "_run_canonical_remote", return_value=unavailable_remote),
                self.assertRaisesRegex(ValueError, "canonical Limen proof-contract authority is unavailable"),
            ):
                RECEIPT._proof_contract_snapshot()

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

    def test_exact_head_runner_uses_a_fresh_clone_instead_of_ignored_source_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "synthetic@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "Synthetic Fixture"], cwd=repository, check=True)
            (repository / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
            (repository / "lock.fixture").write_text("locked dependency fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore", "lock.fixture"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "synthetic fixture"],
                cwd=repository,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
            ).stdout.strip()
            malicious = repository / "node_modules" / "dependency.txt"
            malicious.parent.mkdir()
            malicious.write_text("caller-controlled\n", encoding="utf-8")
            predicate = {
                "argv": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('node_modules/dependency.txt').read_text() == 'locked\\n'",
                ],
                "timeout_seconds": 30,
                "max_output_bytes": 4096,
            }
            runtime_setup = {
                "mode": "locked_install",
                "lockfile": "lock.fixture",
                "argv": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; p=Path('node_modules/dependency.txt'); p.parent.mkdir(); p.write_text('locked\\n')",
                ],
                "timeout_seconds": 30,
                "max_output_bytes": 4096,
            }
            result = RECEIPT._run_isolated_exact_head_predicate(repository, head, predicate, runtime_setup)
            missing_lockfile = copy.deepcopy(runtime_setup)
            missing_lockfile["lockfile"] = "missing.lock"
            missing_result = RECEIPT._run_isolated_exact_head_predicate(
                repository,
                head,
                predicate,
                missing_lockfile,
            )
            marker = repository / "predicate-ran.txt"
            blocked_predicate = {
                **predicate,
                "argv": [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
            }
            failed_setup = {
                **runtime_setup,
                "argv": [sys.executable, "-c", "raise SystemExit(7)"],
            }
            failed_result = RECEIPT._run_isolated_exact_head_predicate(
                repository,
                head,
                blocked_predicate,
                failed_setup,
            )
        self.assertEqual("current_pass", result["classification"], result)
        self.assertEqual(0, result["runtime"]["setup_exit_code"])
        self.assertEqual("lock.fixture", result["runtime"]["lockfile"])
        self.assertRegex(result["runtime"]["lockfile_blob"], r"^[0-9a-f]{40}$")
        self.assertRegex(result["runtime"]["lockfile_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("blocked_external", missing_result["classification"])
        self.assertTrue(any("lockfile" in error for error in missing_result["errors"]))
        self.assertEqual("blocked_external", failed_result["classification"])
        self.assertTrue(any("dependency setup failed" in error for error in failed_result["errors"]))
        self.assertFalse(marker.exists())

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

            timed = {
                **base_request,
                "predicate": {
                    "argv": [sys.executable, "-c", "print('pass')"],
                    "timeout_seconds": 10,
                    "max_output_bytes": 1024,
                },
            }
            with mock.patch.object(
                RECEIPT,
                "_run_isolated_exact_head_predicate",
                side_effect=subprocess.TimeoutExpired([sys.executable], 10),
            ):
                timed_out = run_request(timed)
            self.assertEqual("blocked_external", timed_out["result"])
            self.assertIn("predicate could not start", timed_out["errors"][0])

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
            self.assertTrue(any("isolated exact-head tree changed" in error for error in result["errors"]))

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
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
                "limitations": ["Synthetic fixture only."],
            }
            started = time.monotonic()
            result = run_request(request)
            elapsed = time.monotonic() - started
            self.assertEqual("current_fail", result["result"])
            self.assertTrue(any("live descendant" in error for error in result["errors"]))
            self.assertLess(elapsed, 9)

    def test_redirected_predicate_descendant_is_terminated_before_receipt(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            tempfile.TemporaryDirectory() as remote_temporary,
            tempfile.TemporaryDirectory() as observer_temporary,
        ):
            repository = Path(temporary)
            observer = Path(observer_temporary)
            pid_path = observer / "redirected-child.pid"
            late_path = observer / "late.txt"
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
            child = (
                "import os,time; from pathlib import Path; "
                f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
                f"time.sleep(0.5); Path({str(late_path)!r}).write_text('late')"
            )
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
            wait_for_recorded_process_exit(pid_path)
            self.assertFalse(late_path.exists())

    def test_detached_predicate_descendant_is_terminated_before_receipt(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            tempfile.TemporaryDirectory() as remote_temporary,
            tempfile.TemporaryDirectory() as observer_temporary,
        ):
            repository = Path(temporary)
            observer = Path(observer_temporary)
            pid_path = observer / "detached-grandchild.pid"
            late_path = observer / "detached-late.txt"
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
                "import os,time; from pathlib import Path; "
                f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
                f"time.sleep(0.5); Path({str(late_path)!r}).write_text('late')"
            )
            child = (
                "import subprocess,sys; "
                f"subprocess.Popen([sys.executable,'-c',{grandchild!r}], stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL, start_new_session=True, env={})"
            )
            parent = (
                "import subprocess,sys,time\n"
                "from pathlib import Path\n"
                f"subprocess.Popen([sys.executable,'-c',{child!r}], stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL, start_new_session=True, env={})\n"
                "deadline=time.monotonic()+2\n"
                f"pid_path=Path({str(pid_path)!r})\n"
                "while not pid_path.exists() and time.monotonic()<deadline: time.sleep(0.02)\n"
                "print('parent done')"
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
            wait_for_recorded_process_exit(pid_path)
            self.assertFalse(late_path.exists())


if __name__ == "__main__":
    unittest.main()
