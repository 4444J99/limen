import copy
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
COST_INPUT_ARTIFACT = "scripts/tests/fixtures/positioning-proof/synthetic-cost-failure.json"
COST_REVIEW_ARTIFACT = "scripts/tests/fixtures/positioning-proof/independent-cost-failure-review.json"


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
    hermetic_contract = {
        "repository": request["repository"],
        "default_branch": request["default_branch"],
        "predicate": request["predicate"],
    }
    with mock.patch.object(RECEIPT, "_flagship_contract", return_value=hermetic_contract):
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


def reproduce_cost(payload: dict[str, object], *, reviewed: bool = False) -> dict[str, object]:
    review = independent_cost_review(payload) if reviewed else None
    return COST.reproduce(
        payload,
        input_artifact=COST_INPUT_ARTIFACT,
        review_artifact=COST_REVIEW_ARTIFACT if review is not None else None,
        review_verdict=review,
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
        injected = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.file:///mirror.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
            "GIT_DIR": "/tmp/untrusted.git",
            "GIT_SSL_CAINFO": "/tmp/untrusted-ca.pem",
            "GIT_SSL_NO_VERIFY": "1",
            "GIT_WORK_TREE": "/tmp/untrusted-tree",
            "HTTPS_PROXY": "http://proxy.invalid",
            "https_proxy": "http://lower-proxy.invalid",
            "SSL_CERT_FILE": "/tmp/untrusted-cert.pem",
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
        self.assertEqual("0", options["env"]["GIT_CONFIG_COUNT"])
        self.assertNotIn("GIT_DIR", options["env"])
        self.assertNotIn("GIT_SSL_CAINFO", options["env"])
        self.assertNotIn("GIT_SSL_NO_VERIFY", options["env"])
        self.assertNotIn("GIT_WORK_TREE", options["env"])
        self.assertNotIn("HTTPS_PROXY", options["env"])
        self.assertNotIn("https_proxy", options["env"])
        self.assertNotIn("SSL_CERT_FILE", options["env"])

    def test_predicate_runner_ignores_ambient_path_and_runtime_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_python = Path(directory) / "python3"
            fake_python.write_text("#!/bin/sh\nprintf 'ambient fake\\n'\nexit 0\n", encoding="utf-8")
            fake_python.chmod(0o755)
            with mock.patch.dict(
                os.environ,
                {"PATH": directory, "PYTHONPATH": directory, "NODE_OPTIONS": "--require=/tmp/untrusted.js"},
                clear=False,
            ):
                _argv, environment, metadata = RECEIPT._prepare_predicate_invocation(["python3", "-V"])
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
        self.assertNotIn(directory, environment["PATH"].split(os.pathsep))
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("NODE_OPTIONS", environment)
        invoked_argv = runner.call_args.args[0]
        invoked_environment = runner.call_args.kwargs["environment"]
        self.assertNotEqual(str(fake_python), invoked_argv[0])
        self.assertNotIn(directory, invoked_environment["PATH"].split(os.pathsep))

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
                "--input",
                COST_INPUT_ARTIFACT,
                "--review",
                COST_REVIEW_ARTIFACT,
            ],
            command["argv"],
        )

    def test_cost_failure_population_contract_prevents_cherry_picked_denominators(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        mutations = (
            ("selected_count", 1, "selected_count must equal"),
            ("population_count", 4, "census selection requires"),
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

    def test_cost_failure_population_manifest_and_hash_selection_are_reproduced(self) -> None:
        payload = json.loads((FIXTURES / "synthetic-cost-failure.json").read_text(encoding="utf-8"))
        population = payload["population"]
        seed = "c" * 64
        population["selection_method"] = "deterministic_hash_sample"
        population["selection_rule"] = COST.SELECTION_RULES["deterministic_hash_sample"]
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
        with mock.patch.object(COST.subprocess, "run", return_value=drifted):
            self.assertIsNone(COST._safe_tracked_artifact(artifact))

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
            result = RECEIPT.run_request(request)
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
            result = RECEIPT.run_request(request)
            self.assertEqual("blocked_external", result["result"])
            self.assertTrue(any(expected_error in error for error in result["errors"]))

    def test_receipt_request_binds_selected_flagships_to_contract_owned_predicates(self) -> None:
        contract = RECEIPT._flagship_contract("limen")
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
        self.assertEqual([], RECEIPT.validate_request(request))

        drifted = copy.deepcopy(request)
        drifted["predicate"]["argv"] = [sys.executable, "-c", "print('pass')"]
        errors = RECEIPT.validate_request(drifted)
        self.assertTrue(any("contract-owned flagship command" in error for error in errors), errors)

        unknown = copy.deepcopy(request)
        unknown["flagship_id"] = "arbitrary"
        errors = RECEIPT.validate_request(unknown)
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
        self.assertTrue(any("input is not committed" in error for error in untracked["errors"]))
        self.assertTrue(any("review is not committed" in error for error in untracked["errors"]))

        mutated = copy.deepcopy(payload)
        mutated["rows"][0]["human_minutes"] += 1
        drifted = COST.reproduce(mutated, input_artifact=COST_INPUT_ARTIFACT)
        self.assertTrue(any("input differs from its committed HEAD artifact" in error for error in drifted["errors"]))

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
            child = (
                "import os,time; from pathlib import Path; "
                "Path('redirected-child.pid').write_text(str(os.getpid())); "
                "time.sleep(0.5); Path('late.txt').write_text('late')"
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
            wait_for_recorded_process_exit(repository / "redirected-child.pid")
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
                "import os,time; from pathlib import Path; "
                "Path('detached-grandchild.pid').write_text(str(os.getpid())); "
                "time.sleep(0.5); Path('detached-late.txt').write_text('late')"
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
                "pid_path=Path('detached-grandchild.pid')\n"
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
            wait_for_recorded_process_exit(repository / "detached-grandchild.pid")
            self.assertFalse((repository / "detached-late.txt").exists())


if __name__ == "__main__":
    unittest.main()
