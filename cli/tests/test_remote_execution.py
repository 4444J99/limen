from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

import pytest

from limen.census import Budget, Status, Vendor
from limen.harvest import check_remote_harvest
from limen.io import save_limen_file
from limen.models import BudgetTrack, DispatchLogEntry, LimenFile, Task
from limen.provider_selection import execution_profile_for
from limen.remote_execution import (
    CommandResult,
    DurableOutput,
    GitHubWorkflowAdapter,
    PredicateReceipt,
    ReceiptStore,
    RemoteExecutionError,
    RemoteLifecycle,
    RemoteReceipt,
    RemoteRequest,
    RemoteRun,
    RemoteState,
    _receipt_from_workflow_payload,
    _run_from_actions,
    discover_adapters,
    load_receipt,
    resolve_control_ref,
    verification_context_for_task,
)
from limen.remote_predicate import (
    SANDBOX_IMAGE,
    SANDBOX_OK,
    SANDBOX_OUTPUT_LIMIT,
    SANDBOX_PROFILE_DIGEST,
    PredicateContractError,
    ReceiptTarget,
    _attest_sandbox_runtime,
    _default_sandbox_runner,
    _sandbox_probe_source,
    _validate_repo_paths,
    canonical_json,
    digest_bytes,
    digest_text,
    execute_attested,
    parse_trusted_predicate,
    sandbox_command,
    validate_control_ref,
)
from limen.workstream_contract import packet_contract


SHA = "a" * 40
CONTROL_SHA = "c" * 40
DIGEST = "sha256:" + "b" * 64
NOW = "2026-07-13T00:00:00+00:00"
WORKFLOW_ID = 8675309
WORKFLOW_PATH = ".github/workflows/limen-agent.yml"


def implementation_parent() -> Task:
    return Task(
        id="IMPLEMENT-1",
        title="land implementation",
        repo="organvm/limen",
        type="code",
        target_agent="codex",
        predicate="python3 scripts/check-implementation.py",
        receipt_target="github:organvm/limen:pull-request:7",
        status="done",
        created=date(2026, 7, 12),
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime.fromisoformat(NOW),
                agent="codex",
                session_id="https://github.com/organvm/limen/pull/7",
                status="done",
                output="merged https://github.com/organvm/limen/pull/7",
            )
        ],
    )


def verification_task(task_id: str = "REMOTE-1", **overrides: object) -> Task:
    values: dict[str, object] = {
        "id": task_id,
        "title": "bounded public verification",
        "repo": "organvm/limen",
        "type": "verification",
        "target_agent": "github_actions",
        "predicate": "python3 scripts/check-remote.py",
        "receipt_target": f"artifact:organvm/limen:task:{task_id}",
        "labels": ["mode:verification-only"],
        "depends_on": ["IMPLEMENT-1"],
        "created": date(2026, 7, 13),
    }
    values.update(overrides)
    return Task(**values)  # type: ignore[arg-type]


def verification_context(task_id: str = "REMOTE-1") -> dict[str, object]:
    parent = implementation_parent()
    child = verification_task(task_id)
    return verification_context_for_task(child, {parent.id: parent, child.id: child})


def request(provider: str = "github_actions", **overrides: object) -> RemoteRequest:
    task_id = str(overrides.get("task_id") or "REMOTE-1")
    values: dict[str, object] = {
        "provider": provider,
        "task_id": task_id,
        "repo": "organvm/limen",
        "base_sha": SHA,
        "control_repo": "organvm/limen",
        "control_ref": "main",
        "control_ref_kind": "branch",
        "control_sha": CONTROL_SHA,
        "workflow_id": WORKFLOW_ID,
        "workflow_path": WORKFLOW_PATH,
        "verification_context": verification_context(task_id),
        "predicate": "python3 scripts/check-remote.py",
        "receipt_target": f"artifact:organvm/limen:task:{task_id}",
        "instruction": f"Verify completed implementation for task {task_id}; do not modify code: bounded public verification",
    }
    values.update(overrides)
    return RemoteRequest(**values)  # type: ignore[arg-type]


def run(
    req: RemoteRequest,
    state: RemoteState = RemoteState.RUNNING,
    *,
    run_id: str = "42",
    detail: str = "running",
    observed_at: str = NOW,
) -> RemoteRun:
    return RemoteRun(
        provider=req.provider,
        provider_run_id=run_id,
        url=f"https://github.com/organvm/limen/actions/runs/{run_id}",
        base_sha=req.base_sha,
        control_repo=req.control_repo,
        control_ref=req.control_ref,
        control_ref_kind=req.control_ref_kind,
        control_sha=req.control_sha,
        workflow_id=req.workflow_id,
        workflow_path=req.workflow_path,
        workflow_event=req.workflow_event,
        verification_context_digest=req.verification_context_digest,
        state=state,
        request_id=req.request_id,
        observed_at=observed_at,
        detail=detail,
    )


def output_for(req: RemoteRequest, observed: RemoteRun) -> DurableOutput:
    return DurableOutput(
        kind="artifact",
        uri=observed.url,
        repo="organvm/limen",
        identifier=req.task_id,
    )


def successful_receipt(req: RemoteRequest, observed: RemoteRun) -> RemoteReceipt:
    return RemoteReceipt(
        req,
        observed,
        RemoteState.SUCCEEDED,
        predicate=PredicateReceipt(req.predicate_digest, True, 0, DIGEST),
        outputs=(output_for(req, observed),),
        observed_sha=req.base_sha,
        observed_at=observed.observed_at,
    )


@pytest.mark.parametrize(
    "target",
    [
        "pull-request",
        "github:organvm/limen:pull-request:REMOTE-1",
        "github:organvm/limen:unknown:7",
        "https://github.com/organvm/limen/pull/7",
        "artifact:organvm/limen:task:REMOTE-1:extra",
    ],
)
def test_request_rejects_unknown_or_symbolic_receipt_targets(target: str) -> None:
    with pytest.raises(ValueError, match="receipt_target|target|numeric"):
        request(receipt_target=target)


def test_request_rejects_nonfinite_profile_and_model_pins() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        request(execution_profile={"reasoning_depth": float("nan")})
    with pytest.raises(ValueError, match="model or tier"):
        request(execution_profile={"model_id": "hard-coded"})


def test_request_id_changes_with_control_sha_workflow_or_verification_context() -> None:
    baseline = request()
    assert request(control_ref="release", control_ref_kind="tag").request_id != baseline.request_id
    assert request(control_sha="d" * 40).request_id != baseline.request_id
    assert request(workflow_id=WORKFLOW_ID + 1).request_id != baseline.request_id
    changed = verification_context()
    changed["mode"] = "tampered"
    with pytest.raises(ValueError, match="verification context"):
        request(verification_context=changed)

    mutable_context = verification_context()
    mutable_profile: dict[str, object] = {"reasoning_depth": 2}
    frozen = request(verification_context=mutable_context, execution_profile=mutable_profile)
    frozen_id = frozen.request_id
    mutable_context["mode"] = "mutated-after-construction"
    mutable_profile["reasoning_depth"] = 99
    assert frozen.request_id == frozen_id


@pytest.mark.parametrize(
    "value",
    ["HEAD", "head", SHA, "refs/pull/7/head", "refs/heads/main", "bad ref", "../main", "main.lock"],
)
def test_control_ref_rejects_symbolic_sha_pull_and_unsafe_names(value: str) -> None:
    with pytest.raises(PredicateContractError, match="explicit safe branch or tag"):
        validate_control_ref(value, "branch")


def test_verification_context_requires_terminal_same_repo_implementation_custody() -> None:
    child = verification_task()

    parent = implementation_parent()
    parent.status = "in_progress"
    with pytest.raises(RemoteExecutionError, match="terminal implementation custody"):
        verification_context_for_task(child, {parent.id: parent, child.id: child})

    parent = implementation_parent()
    parent.repo = "other/repo"
    parent.receipt_target = "github:other/repo:pull-request:7"
    parent.dispatch_log[-1].output = "merged https://github.com/other/repo/pull/7"
    with pytest.raises(RemoteExecutionError, match="child target repo"):
        verification_context_for_task(child, {parent.id: parent, child.id: child})

    parent = implementation_parent()
    parent.dispatch_log[-1].output = "opened https://github.com/organvm/limen/pull/7"
    with pytest.raises(RemoteExecutionError, match="terminal custody event"):
        verification_context_for_task(child, {parent.id: parent, child.id: child})


def test_request_rejects_malformed_direct_verification_custody_context() -> None:
    context = verification_context()
    rows = context["implementation_custody"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    rows[0]["receipt_target"] = "github:organvm/limen:issue:7"
    with pytest.raises(ValueError, match="exact implementation custody"):
        request(verification_context=context)


@pytest.mark.parametrize(
    ("target", "identity"),
    [
        (
            "github:organvm/limen:pull-request:7",
            {
                "kind": "pull_request",
                "uri": "https://github.com/organvm/limen/pull/7",
                "repo": "organvm/limen",
                "identifier": "7",
                "path": "",
            },
        ),
        (
            "github:organvm/limen:issue:9",
            {
                "kind": "issue",
                "uri": "https://github.com/organvm/limen/issues/9",
                "repo": "organvm/limen",
                "identifier": "9",
                "path": "",
            },
        ),
        (
            f"github:organvm/limen:commit:{SHA}",
            {
                "kind": "commit",
                "uri": f"https://github.com/organvm/limen/commit/{SHA}",
                "repo": "organvm/limen",
                "identifier": SHA,
                "path": "",
            },
        ),
        (
            f"github:organvm/limen:blob:{SHA}:docs/proof.md",
            {
                "kind": "blob",
                "uri": f"https://github.com/organvm/limen/blob/{SHA}/docs/proof.md",
                "repo": "organvm/limen",
                "identifier": SHA,
                "path": "docs/proof.md",
            },
        ),
    ],
)
def test_receipt_target_matches_only_exact_typed_identity(target: str, identity: dict[str, object]) -> None:
    parsed = ReceiptTarget.parse(target)
    assert parsed.matches(identity)
    assert not parsed.matches({**identity, "repo": "other/repo"})
    assert not parsed.matches({**identity, "identifier": "999"})
    assert not parsed.matches({**identity, "uri": "https://example.com/spoof"})


def test_artifact_completion_binds_current_run_not_any_same_repo_run() -> None:
    req = request()
    observed = run(req, RemoteState.SUCCEEDED)
    assert successful_receipt(req, observed).done

    other = replace(output_for(req, observed), uri="https://github.com/organvm/limen/actions/runs/99")
    receipt = replace(successful_receipt(req, observed), outputs=(other,))
    assert not receipt.done


def test_receipt_state_must_equal_embedded_run_state() -> None:
    req = request()
    failed = run(req, RemoteState.FAILED)
    with pytest.raises(ValueError, match="state does not match"):
        RemoteReceipt(req, failed, RemoteState.SUCCEEDED)
    with pytest.raises(ValueError, match="provider/request/target/control/workflow"):
        RemoteReceipt(req, replace(failed, request_id="c" * 32), RemoteState.FAILED)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests && echo pass",
        "pytest cli/tests; true",
        "pytest cli/tests | tee out",
        "pytest cli/tests > out",
        "pytest $(printf cli/tests)",
        "pytest `printf cli/tests`",
        "pytest cli/tests\nprintf bad",
        "pytest --help",
        "pytest --collect-only cli/tests",
        "ruff --version",
        "make -n test",
        "cargo test --no-run",
        "pytest @/tmp/args",
        "pytest cli/tests --rootdir=/tmp",
        "bash -lc scripts/verify.sh",
        "curl https://example.com",
        "python3 -m pytest /Volumes/Archive/tests",
        "python3 -m pytest .limen-private/tests",
        "python3 -m pytest cli/tests/test_remote_execution.py -q",
        "ruff check cli/src",
        "python3 -m mypy cli/src",
        "bash scripts/verify-whole.sh",
        "python3 scripts/build-release.py",
        "python3 scripts/check-agent-docs.py --fix",
        "npm test",
        "make verify",
        "cargo clippy",
        "go test ./...",
    ],
)
def test_remote_predicate_rejects_shell_and_semantic_bypasses(predicate: str) -> None:
    with pytest.raises(PredicateContractError):
        parse_trusted_predicate(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "python3 scripts/check-agent-docs.py",
        "python3 scripts/verify-receipt.py",
        "python3 tools/check_policy.py",
        "python3 tools/verify.py",
    ],
)
def test_remote_predicate_accepts_narrow_positive_grammars(predicate: str) -> None:
    assert parse_trusted_predicate(predicate).argv


def _git_repo(tmp_path: Path, script: str) -> tuple[Path, str]:
    repo = tmp_path / "target"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "verify.py").write_text(script)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "scripts/verify.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return repo, sha


def _worker_args(repo: Path, req: RemoteRequest, packet_digest: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        request_id=req.request_id,
        provider=req.provider,
        task_id=req.task_id,
        repo=req.repo,
        control_repo=req.control_repo,
        control_ref=req.control_ref,
        control_ref_kind=req.control_ref_kind,
        base_sha=req.base_sha,
        control_sha=req.control_sha,
        workflow_id=req.workflow_id,
        workflow_path=req.workflow_path,
        workflow_event=req.workflow_event,
        observed_control_repo=req.control_repo,
        observed_control_ref=req.control_ref,
        observed_control_ref_kind=req.control_ref_kind,
        observed_workflow_event=req.workflow_event,
        observed_workflow_ref=(
            f"{req.control_repo}/{req.workflow_path}@refs/"
            f"{'heads' if req.control_ref_kind == 'branch' else 'tags'}/{req.control_ref}"
        ),
        observed_workflow_sha=req.control_sha,
        verification_context_digest=req.verification_context_digest,
        predicate=req.predicate,
        instruction_digest=digest_text(req.instruction),
        receipt_target=req.receipt_target,
        custody_mode=req.custody_mode,
        inputs_json="[]",
        execution_profile_json="{}",
        packet_digest=packet_digest or req.packet_digest,
        run_url="https://github.com/organvm/limen/actions/runs/42",
        cwd=str(repo),
        control_cwd=str(repo),
        output=str(repo.parent / "receipt.json"),
        timeout=30,
        docker_binary="docker-fixture",
    )


def fake_sandbox_runner(
    *,
    predicate_stdout: bytes = b"verified\n",
    predicate_returncode: int = 0,
) -> tuple[Callable[[Sequence[str], int], subprocess.CompletedProcess[bytes]], list[tuple[str, ...]]]:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: int) -> subprocess.CompletedProcess[bytes]:
        args = tuple(argv)
        calls.append(args)
        if args[1:3] == ("version", "--format"):
            return subprocess.CompletedProcess(args, 0, b"27.0.0\n")
        if args[1:3] == ("image", "inspect"):
            return subprocess.CompletedProcess(args, 0, json.dumps([SANDBOX_IMAGE]).encode() + b"\n")
        if args[-1] == "/workspace/scripts/check-limen-sandbox.py":
            return subprocess.CompletedProcess(args, 0, SANDBOX_OK)
        return subprocess.CompletedProcess(args, predicate_returncode, predicate_stdout)

    return runner, calls


def test_worker_recomputes_packet_and_emits_counts_only_receipt(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    runner, calls = fake_sandbox_runner()
    receipt = execute_attested(_worker_args(repo, req), sandbox_runner=runner)

    assert receipt["predicate_exit_code"] == 0
    assert receipt["workspace_clean"] is True
    assert receipt["instruction_digest"] == digest_text(req.instruction)
    assert receipt["control_sha"] == sha == receipt["observed_control_sha"]
    assert receipt["workflow_id"] == WORKFLOW_ID
    assert receipt["sandbox_image"] == SANDBOX_IMAGE
    assert receipt["sandbox_profile_digest"] == SANDBOX_PROFILE_DIGEST
    assert any("--network=none" in call for call in calls)
    assert req.predicate not in json.dumps(receipt)
    unsigned = dict(receipt)
    claimed = unsigned.pop("receipt_digest")
    assert claimed == digest_bytes(canonical_json(unsigned))

    with pytest.raises(PredicateContractError, match="packet digest mismatch"):
        execute_attested(_worker_args(repo, req, DIGEST), sandbox_runner=runner)


def test_worker_rejects_observed_workflow_sha_that_differs_from_control_commit(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    args = _worker_args(repo, req)
    args.observed_workflow_sha = "d" * 40
    runner, _calls = fake_sandbox_runner()
    with pytest.raises(PredicateContractError, match="workflow SHA"):
        execute_attested(args, sandbox_runner=runner)


def test_worker_rejects_observed_branch_that_differs_from_control_ref(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    args = _worker_args(repo, req)
    args.observed_control_ref = "other"
    runner, _calls = fake_sandbox_runner()
    with pytest.raises(PredicateContractError, match="branch/tag"):
        execute_attested(args, sandbox_runner=runner)


def test_worker_rejects_syntactically_valid_request_id_not_derived_from_packet(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    args = _worker_args(repo, req)
    args.request_id = "f" * 32
    runner, _calls = fake_sandbox_runner()
    with pytest.raises(PredicateContractError, match="recomputed packet digest"):
        execute_attested(args, sandbox_runner=runner)


@pytest.mark.parametrize(
    "observed_workflow_ref",
    [
        "organvm/limen/.github/workflows/limen-agent.yml@refs/heads/other",
        "organvm/limen/.github/workflows/limen-agent.yml@refs/tags/main",
        "organvm/limen/.github/workflows/other.yml@refs/heads/main",
        f"organvm/limen/.github/workflows/limen-agent.yml@{'d' * 40}",
    ],
)
def test_worker_rejects_workflow_ref_contradicting_packet(
    tmp_path: Path,
    observed_workflow_ref: str,
) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    args = _worker_args(repo, req)
    args.observed_workflow_ref = observed_workflow_ref
    runner, _calls = fake_sandbox_runner()
    with pytest.raises(PredicateContractError, match="workflow path and control ref"):
        execute_attested(args, sandbox_runner=runner)


def test_worker_accepts_tag_workflow_ref_and_rejects_heads_suffix_for_tag(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(
        base_sha=sha,
        control_ref="release-v1",
        control_ref_kind="tag",
        control_sha=sha,
        predicate="python3 scripts/verify.py",
    )
    runner, _calls = fake_sandbox_runner()
    receipt = execute_attested(_worker_args(repo, req), sandbox_runner=runner)
    assert receipt["control_ref_kind"] == "tag"

    args = _worker_args(repo, req)
    args.observed_workflow_ref = f"{req.control_repo}/{req.workflow_path}@refs/heads/{req.control_ref}"
    with pytest.raises(PredicateContractError, match="workflow path and control ref"):
        execute_attested(args, sandbox_runner=runner)


def test_worker_rejects_symlinked_verifier_outside_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "target"
    (repo / "scripts").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("raise SystemExit(0)\n")
    (repo / "scripts" / "verify.py").symlink_to(outside)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "scripts/verify.py"], cwd=repo, check=True)
    predicate = parse_trusted_predicate("python3 scripts/verify.py")
    with pytest.raises(PredicateContractError, match="escapes|symlink"):
        _validate_repo_paths(predicate, repo.resolve())


def test_worker_scans_preexisting_untracked_secret_and_refuses_clean_receipt(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    (repo / "leak.txt").write_text("API_KEY=plaintext-secret")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    runner, _calls = fake_sandbox_runner()
    receipt = execute_attested(_worker_args(repo, req), sandbox_runner=runner)
    assert receipt["predicate_exit_code"] != 0
    assert receipt["delta_safe"] is False
    assert receipt["workspace_clean"] is False


def test_sandbox_command_exposes_only_read_only_target_and_controlled_tmpfs(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check-safe.py").write_text("raise SystemExit(0)\n")
    command = sandbox_command(tmp_path, "scripts/check-safe.py")
    joined = " ".join(command)

    assert command.count("--mount") == 1
    assert any(f"src={tmp_path.resolve()},dst=/workspace,readonly" in token for token in command)
    assert "/var/run/docker.sock" not in joined
    assert ".limen-control" not in joined
    assert "--network=none" in command
    assert "--log-driver=local" in command
    assert "--log-opt=max-size=1m" in command
    assert "--log-opt=max-file=1" in command
    assert "--log-opt=compress=false" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges:true" in command
    assert "--tmpfs" in command
    assert "/tmp:rw,noexec,nosuid,nodev,size=67108864,mode=1777" in command
    assert "-i" in command
    assert not any(token.startswith("GITHUB_") for token in command)


def test_boundary_probe_covers_env_secret_sibling_outside_write_and_network() -> None:
    source = _sandbox_probe_source()
    for marker in (
        "GITHUB_STEP_SUMMARY",
        'key.startswith("GITHUB_")',
        "host-secret-must-not-cross",
        ".limen-control",
        'Path("/outside-write")',
        "limen-outside-write",
        "socket.if_nameindex()",
        'connect_ex(("198.51.100.1", 9))',
        'Path("/tmp/limen-sandbox-probe")',
    ):
        assert marker in source


def test_sandbox_runtime_and_output_limits_fail_closed(tmp_path: Path) -> None:
    repo, sha = _git_repo(tmp_path, "raise SystemExit(0)\n")
    req = request(base_sha=sha, control_sha=sha, predicate="python3 scripts/verify.py")
    runner, _calls = fake_sandbox_runner(predicate_stdout=b"x" * (SANDBOX_OUTPUT_LIMIT + 1))
    receipt = execute_attested(_worker_args(repo, req), sandbox_runner=runner)
    assert receipt["predicate_exit_code"] == 125

    def unavailable(argv: Sequence[str], _timeout: int) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(tuple(argv), 1, b"")

    with pytest.raises(PredicateContractError, match="Docker daemon unavailable"):
        _attest_sandbox_runtime(unavailable, docker_binary="docker")

    def wrong_digest(argv: Sequence[str], _timeout: int) -> subprocess.CompletedProcess[bytes]:
        args = tuple(argv)
        if args[1:3] == ("version", "--format"):
            return subprocess.CompletedProcess(args, 0, b"27.0.0\n")
        return subprocess.CompletedProcess(args, 0, b'["python@sha256:' + (b"0" * 64) + b'"]\n')

    with pytest.raises(PredicateContractError, match="allowlisted official digest"):
        _attest_sandbox_runtime(wrong_digest, docker_binary="docker")


def test_real_sandbox_blocks_outside_write_github_env_sibling_secret_and_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mandatory = sys.platform.startswith("linux") and os.environ.get("CI", "").lower() == "true"
    docker = shutil.which("docker")
    if docker is None:
        if mandatory:
            pytest.fail("Linux CI requires Docker CLI for the mandatory containment integration")
        pytest.skip("Docker CLI unavailable")
    available = subprocess.run(
        [docker, "image", "inspect", SANDBOX_IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if available.returncode != 0:
        if not mandatory:
            pytest.skip("exact pinned sandbox image is not present locally")
        pulled = subprocess.run(
            [docker, "pull", SANDBOX_IMAGE],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert pulled.returncode == 0, f"mandatory sandbox image pull failed: {pulled.stderr[-500:]}"
    target = tmp_path / "target-probe"
    (target / "scripts").mkdir(parents=True)
    (target / "scripts" / "check-limen-sandbox.py").write_text(_sandbox_probe_source())
    (tmp_path / ".limen-control").mkdir()
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))
    monkeypatch.setenv("TEST_ENV_SECRET", "host-secret-must-not-cross")
    _attest_sandbox_runtime(_default_sandbox_runner, docker_binary=docker)
    result = _default_sandbox_runner(
        sandbox_command(target, "scripts/check-limen-sandbox.py", docker_binary=docker),
        30,
    )
    assert result.returncode == 0
    assert result.stdout == SANDBOX_OK


def test_receipt_store_validates_filename_content_and_live_contract(tmp_path: Path) -> None:
    req = request()
    observed = run(req)
    store = ReceiptStore(tmp_path)
    path = store.write(RemoteReceipt(req, observed, observed.state, observed_at=NOW, detail=observed.detail))
    assert load_receipt(path, req).run == observed

    payload = json.loads(path.read_text())
    payload["detail"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(RemoteExecutionError, match="filename/content hash"):
        load_receipt(path, req)

    other = request(predicate="python3 scripts/check-harvest.py")
    with pytest.raises(RemoteExecutionError, match="manifest"):
        load_receipt(store.write(RemoteReceipt(req, observed, observed.state)), other)


class StableAdapter:
    def __init__(self, req: RemoteRequest) -> None:
        self.provider = req.provider
        self.req = req
        self.submissions = 0

    def preflight(self, _request: RemoteRequest) -> None:
        return None

    def intent(self, _request: RemoteRequest) -> RemoteRun:
        return run(self.req, RemoteState.SUBMITTED, run_id=f"pending:{self.req.request_id}")

    def submit(self, _request: RemoteRequest) -> RemoteRun:
        self.submissions += 1
        return self.intent(_request)

    def probe(self, _request: RemoteRequest, current: RemoteRun) -> RemoteRun:
        return current

    def harvest(self, _request: RemoteRequest, current: RemoteRun) -> RemoteReceipt:
        return RemoteReceipt(self.req, current, current.state, observed_at=current.observed_at)

    def recover(self, _request: RemoteRequest, current: RemoteRun) -> RemoteRun:
        return current


def test_lifecycle_persists_intent_and_reuses_attempt_without_duplicate_submit(tmp_path: Path) -> None:
    req = request()
    adapter = StableAdapter(req)
    lifecycle = RemoteLifecycle(adapter, ReceiptStore(tmp_path))

    first, first_path = lifecycle.submit(req)
    second, second_path = lifecycle.submit(req)

    assert adapter.submissions == 1
    assert first.request_id == req.request_id == second.request_id
    assert first_path == second_path


def test_lifecycle_rechecks_guard_after_preflight_before_provider_submit(tmp_path: Path) -> None:
    req = request()
    adapter = StableAdapter(req)
    lifecycle = RemoteLifecycle(adapter, ReceiptStore(tmp_path))

    def expired_boundary() -> None:
        raise RemoteExecutionError("workstream runway is exhausted")

    with pytest.raises(RemoteExecutionError, match="runway is exhausted"):
        lifecycle.submit(req, before_submit=expired_boundary)

    assert adapter.submissions == 0
    assert list(tmp_path.rglob("*.json")) == []


def test_lifecycle_rejects_provider_identity_changes(tmp_path: Path) -> None:
    req = request()
    adapter = StableAdapter(req)
    current = run(req)
    adapter.probe = lambda _request, _run: replace(current, provider_run_id="99")  # type: ignore[method-assign]
    with pytest.raises(RemoteExecutionError, match="run identity"):
        RemoteLifecycle(adapter, ReceiptStore(tmp_path)).probe(req, current)


def vendor(name: str = "renamed-actions") -> Vendor:
    return Vendor(
        name=name,
        aliases=(),
        binary="gh-fixture",
        kind="github-actions",
        local_checkout=False,
        issue_assignment=False,
        auth_mode="fixture",
        cred_ref=None,
        meter="none",
        tiering="none",
        budget=Budget(None, "runs", "none", "test", "unmodeled"),
        status=Status(True, "live", "fixture"),
    )


def control_ref_result(
    args: tuple[str, ...],
    *,
    ref: str = "main",
    sha: str = CONTROL_SHA,
) -> CommandResult | None:
    if args[1:] == ("api", "repos/organvm/limen", "--jq", ".default_branch"):
        return CommandResult(args, 0, ref + "\n")
    if f"/git/ref/heads/{ref}" in " ".join(args):
        return CommandResult(
            args,
            0,
            json.dumps({"ref": f"refs/heads/{ref}", "object": {"type": "commit", "sha": sha}}),
        )
    if f"/git/ref/tags/{ref}" in " ".join(args):
        return CommandResult(args, 1, "", "not found")
    if f"/commits/{ref}" in " ".join(args):
        return CommandResult(args, 0, sha + "\n")
    if f"/branches/{ref}" in " ".join(args):
        return CommandResult(
            args,
            0,
            json.dumps({"name": ref, "protected": True, "commit": {"sha": sha}}),
        )
    return None


def test_control_ref_resolution_uses_exact_branch_namespace_and_peeled_commit() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        calls.append(args)
        return control_ref_result(args) or CommandResult(args, 1, "", "unexpected")

    assert resolve_control_ref("organvm/limen", "main", kind="branch", runner=runner, gh="gh") == (
        "branch",
        CONTROL_SHA,
    )
    assert any("/git/ref/heads/main" in " ".join(args) for args in calls)
    assert any("/commits/main" in " ".join(args) for args in calls)
    before = len(calls)
    for unsafe in ("HEAD", SHA, "refs/pull/7/head"):
        with pytest.raises(RemoteExecutionError, match="explicit safe branch or tag"):
            resolve_control_ref("organvm/limen", unsafe, kind="branch", runner=runner, gh="gh")
    assert len(calls) == before


def test_control_ref_resolution_rejects_ambiguous_branch_and_tag_name() -> None:
    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        joined = " ".join(args)
        if "/git/ref/heads/release" in joined:
            payload = {"ref": "refs/heads/release", "object": {"type": "commit", "sha": CONTROL_SHA}}
            return CommandResult(args, 0, json.dumps(payload))
        if "/git/ref/tags/release" in joined:
            payload = {"ref": "refs/tags/release", "object": {"type": "commit", "sha": CONTROL_SHA}}
            return CommandResult(args, 0, json.dumps(payload))
        return CommandResult(args, 1)

    with pytest.raises(RemoteExecutionError, match="ambiguous branch/tag"):
        resolve_control_ref("organvm/limen", "release", runner=runner, gh="gh")


def test_control_ref_resolution_requires_protected_branch() -> None:
    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        if "/branches/main" in " ".join(args):
            payload = {"name": "main", "protected": False, "commit": {"sha": CONTROL_SHA}}
            return CommandResult(args, 0, json.dumps(payload))
        return control_ref_result(args) or CommandResult(args, 1)

    with pytest.raises(RemoteExecutionError, match="unprotected"):
        resolve_control_ref("organvm/limen", "main", kind="branch", runner=runner, gh="gh")


def test_discovery_preserves_explicit_empty_catalog() -> None:
    called = False

    def runner(argv: object, timeout: int) -> CommandResult:
        nonlocal called
        called = True
        return CommandResult((), 0)

    adapters, capabilities = discover_adapters(vendors=(), runner=runner)
    assert adapters == {}
    assert capabilities == []
    assert called is False


def test_discovery_accepts_renamed_live_github_actions_vendor() -> None:
    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        if result := control_ref_result(args):
            return result
        if "actions/workflows" in " ".join(args):
            return CommandResult(
                args,
                0,
                json.dumps({"id": WORKFLOW_ID, "path": WORKFLOW_PATH, "state": "active"}),
            )
        return CommandResult(args, 0)

    adapters, capabilities = discover_adapters(
        vendors=(vendor(),),
        runner=runner,
        binary_finder=lambda _name: "/fixture/gh",
    )
    assert adapters["renamed-actions"].provider == "renamed-actions"
    assert adapters["renamed-actions"].control_sha == CONTROL_SHA  # type: ignore[attr-defined]
    assert capabilities[0].reachable is True


@pytest.mark.parametrize(("auth_rc", "workflow_rc"), [(1, 0), (0, 1)])
def test_discovery_does_not_advertise_unreachable_auth_or_workflow(auth_rc: int, workflow_rc: int) -> None:
    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        if "auth" in args:
            return CommandResult(args, auth_rc)
        if result := control_ref_result(args):
            return result
        return CommandResult(
            args, workflow_rc, json.dumps({"id": WORKFLOW_ID, "path": WORKFLOW_PATH, "state": "active"})
        )

    adapters, capabilities = discover_adapters(
        vendors=(vendor(),),
        runner=runner,
        binary_finder=lambda _name: "/fixture/gh",
    )
    assert adapters == {}
    assert capabilities[0].reachable is False


def _actions_adapter(runner, provider: str = "github_actions") -> GitHubWorkflowAdapter:
    return GitHubWorkflowAdapter(
        provider=provider,
        control_repo="organvm/limen",
        control_sha=CONTROL_SHA,
        control_ref="main",
        control_ref_kind="branch",
        workflow_id=WORKFLOW_ID,
        workflow_path=WORKFLOW_PATH,
        runner=runner,
        gh_binary="gh",
    )


def exact_actions_row(
    req: RemoteRequest,
    *,
    run_id: int = 42,
    status: str = "queued",
    conclusion: str | None = None,
) -> dict[str, object]:
    return {
        "id": run_id,
        "html_url": f"https://github.com/{req.control_repo}/actions/runs/{run_id}",
        "display_title": f"remote:{req.request_id}:{req.task_id}",
        "head_branch": req.control_ref,
        "head_sha": req.control_sha,
        "event": req.workflow_event,
        "repository": {"full_name": req.control_repo},
        "workflow_id": req.workflow_id,
        "path": req.workflow_path,
        "status": status,
        "conclusion": conclusion,
    }


def preflight_result(args: tuple[str, ...], *, private: bool = False) -> CommandResult | None:
    joined = " ".join(args)
    if result := control_ref_result(args):
        return result
    if f"repos/organvm/limen/actions/workflows/{WORKFLOW_ID}" in args:
        return CommandResult(args, 0, json.dumps({"id": WORKFLOW_ID, "path": WORKFLOW_PATH, "state": "active"}))
    if args[1:3] == ("api", "repos/organvm/limen"):
        return CommandResult(args, 0, "true\n" if private else "false\n")
    if "/pulls/7" in joined:
        return CommandResult(args, 0, "2026-07-13T00:00:00Z\n")
    return None


def test_private_target_fails_closed_before_workflow_mutation() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        calls.append(args)
        return preflight_result(args, private=True) or CommandResult(args, 1)

    with pytest.raises(RemoteExecutionError, match="private target blocked"):
        _actions_adapter(runner).submit(request())
    assert not any(args[1:3] == ("workflow", "run") for args in calls)


def test_control_head_advance_during_catalog_lookup_stops_workflow_mutation() -> None:
    calls: list[tuple[str, ...]] = []
    control_probes = 0

    def runner(argv: object, _timeout: int) -> CommandResult:
        nonlocal control_probes
        args = tuple(argv)  # type: ignore[arg-type]
        calls.append(args)
        joined = " ".join(args)
        if "/git/ref/heads/main" in joined:
            control_probes += 1
            sha = CONTROL_SHA if control_probes == 1 else "d" * 40
            return CommandResult(
                args,
                0,
                json.dumps({"ref": "refs/heads/main", "object": {"type": "commit", "sha": sha}}),
            )
        if "/commits/main" in joined:
            return CommandResult(args, 0, (CONTROL_SHA if control_probes == 1 else "d" * 40) + "\n")
        if "/branches/main" in joined:
            sha = CONTROL_SHA if control_probes == 1 else "d" * 40
            return CommandResult(args, 0, json.dumps({"name": "main", "protected": True, "commit": {"sha": sha}}))
        if result := preflight_result(args):
            return result
        if args[1] == "api":
            return CommandResult(args, 0, '[{"workflow_runs": []}]')
        raise AssertionError(args)

    with pytest.raises(RemoteExecutionError, match="advanced"):
        _actions_adapter(runner).submit(request())
    assert control_probes == 2
    assert not any(args[1:3] == ("workflow", "run") for args in calls)


def test_lifecycle_discards_unmutated_intent_when_state_changes_during_persist(tmp_path: Path) -> None:
    guard_calls = 0
    workflow_mutations = 0

    def runner(argv: object, _timeout: int) -> CommandResult:
        nonlocal workflow_mutations
        args = tuple(argv)  # type: ignore[arg-type]
        if result := preflight_result(args):
            return result
        if args[1:3] == ("workflow", "run"):
            workflow_mutations += 1
            return CommandResult(args, 0)
        if args[1] == "api":
            return CommandResult(args, 0, '[{"workflow_runs": []}]')
        raise AssertionError(args)

    class StateAdvancingStore(ReceiptStore):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.board_generation = 0
            self.advance_on_intent = True

        def write(self, receipt: RemoteReceipt) -> Path:
            path = super().write(receipt)
            if self.advance_on_intent and receipt.detail == "submission intent persisted before provider mutation":
                self.advance_on_intent = False
                self.board_generation += 1
            return path

    store = StateAdvancingStore(tmp_path)
    expected_generation = 0

    def authoritative_guard() -> None:
        nonlocal guard_calls
        guard_calls += 1
        if store.board_generation != expected_generation:
            raise RemoteExecutionError("authoritative board changed while intent was persisted")

    lifecycle = RemoteLifecycle(_actions_adapter(runner), store)
    req = request()
    with pytest.raises(RemoteExecutionError, match="board changed"):
        lifecycle.submit(req, before_submit=authoritative_guard)

    assert guard_calls == 2
    assert workflow_mutations == 0
    assert list(tmp_path.rglob("*.json")) == []

    expected_generation = store.board_generation
    observed, _receipt_path = lifecycle.submit(req, before_submit=authoritative_guard)

    assert observed.pending_identity
    assert guard_calls == 4
    assert workflow_mutations == 1

    recovered, _recovered_path = lifecycle.submit(req, before_submit=authoritative_guard)

    assert recovered.pending_identity
    assert guard_calls == 4
    assert workflow_mutations == 1


def test_workflow_submission_correlates_exact_request_across_paginated_catalog() -> None:
    list_calls = 0

    def runner(argv: object, _timeout: int) -> CommandResult:
        nonlocal list_calls
        args = tuple(argv)  # type: ignore[arg-type]
        if result := preflight_result(args):
            return result
        if args[1:3] == ("workflow", "run"):
            assert args[args.index("--ref") + 1] == "main"
            assert CONTROL_SHA not in args[: args.index("-f")]
            return CommandResult(args, 0)
        if args[1] == "api":
            list_calls += 1
            if list_calls == 1:
                return CommandResult(args, 0, '[{"workflow_runs": []}]')
            req = request()
            payload = [
                {
                    "workflow_runs": [
                        {
                            "id": 11,
                            "html_url": "https://github.com/organvm/limen/actions/runs/11",
                            "display_title": "remote:other:T",
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                },
                {"workflow_runs": [exact_actions_row(req, run_id=22)]},
            ]
            return CommandResult(args, 0, json.dumps(payload))
        raise AssertionError(args)

    observed = _actions_adapter(runner).submit(request())
    assert observed.provider_run_id == "22"
    assert observed.request_id == request().request_id


def test_post_submission_lookup_failure_returns_recoverable_pending_identity() -> None:
    list_calls = 0

    def runner(argv: object, _timeout: int) -> CommandResult:
        nonlocal list_calls
        args = tuple(argv)  # type: ignore[arg-type]
        if result := preflight_result(args):
            return result
        if args[1:3] == ("workflow", "run"):
            return CommandResult(args, 0)
        if args[1] == "api":
            list_calls += 1
            return CommandResult(args, 0 if list_calls == 1 else 1, '[{"workflow_runs": []}]', "network")
        raise AssertionError(args)

    observed = _actions_adapter(runner).submit(request())
    assert observed.pending_identity
    assert observed.request_id == request().request_id


def test_terminal_workflow_failure_requires_no_artifact() -> None:
    req = request()
    current = run(req)
    calls: list[tuple[str, ...]] = []

    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        calls.append(args)
        payload = exact_actions_row(req, status="completed", conclusion="failure")
        return CommandResult(args, 0, json.dumps(payload))

    receipt = _actions_adapter(runner).harvest(req, current)
    assert receipt.state is RemoteState.FAILED
    assert not any(args[1:3] == ("run", "download") for args in calls)


def test_successful_workflow_without_artifact_is_blocked() -> None:
    req = request()
    current = run(req)

    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        if args[1] == "api":
            payload = exact_actions_row(req, status="completed", conclusion="success")
            return CommandResult(args, 0, json.dumps(payload))
        return CommandResult(args, 1, "", "artifact absent")

    receipt = _actions_adapter(runner).harvest(req, current)
    assert receipt.state is RemoteState.BLOCKED
    assert not receipt.done


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("head_branch", None),
        ("head_branch", ""),
        ("head_branch", "other"),
        ("head_sha", "d" * 40),
        ("event", "push"),
        ("repository", {"full_name": "other/repo"}),
        ("workflow_id", WORKFLOW_ID + 1),
        ("path", ".github/workflows/other.yml"),
    ],
)
def test_actions_run_rejects_contradictory_head_event_repo_or_workflow(field: str, value: object) -> None:
    req = request()
    row = exact_actions_row(req)
    row[field] = value
    with pytest.raises(RemoteExecutionError, match="control ref/SHA, event, repository, workflow"):
        _run_from_actions(req, req.request_id, row, req.control_repo)


def test_actions_catalog_fails_closed_on_request_id_identity_collision() -> None:
    req = request()
    row = exact_actions_row(req)
    row["head_sha"] = "d" * 40

    def runner(argv: object, _timeout: int) -> CommandResult:
        args = tuple(argv)  # type: ignore[arg-type]
        return CommandResult(args, 0, json.dumps([{"workflow_runs": [row]}]))

    with pytest.raises(RemoteExecutionError, match="identity collision"):
        _actions_adapter(runner)._find_run(req, req.request_id)


def workflow_payload(req: RemoteRequest, observed: RemoteRun) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "limen.remote-execution.v3",
        "request_id": observed.request_id,
        "provider": req.provider,
        "task_id": req.task_id,
        "repo": req.repo,
        "base_sha": req.base_sha,
        "observed_sha": req.base_sha,
        "control_repo": req.control_repo,
        "control_ref": req.control_ref,
        "control_ref_kind": req.control_ref_kind,
        "control_sha": req.control_sha,
        "observed_control_sha": req.control_sha,
        "observed_control_ref": req.control_ref,
        "observed_control_ref_kind": req.control_ref_kind,
        "workflow_id": req.workflow_id,
        "workflow_path": req.workflow_path,
        "observed_workflow_path": req.workflow_path,
        "workflow_event": req.workflow_event,
        "observed_workflow_event": req.workflow_event,
        "observed_workflow_sha": req.control_sha,
        "verification_context_digest": req.verification_context_digest,
        "predicate_digest": req.predicate_digest,
        "instruction_digest": digest_text(req.instruction),
        "predicate_exit_code": 0,
        "predicate_output_digest": DIGEST,
        "packet_digest": req.packet_digest,
        "receipt_target": req.receipt_target,
        "custody_mode": req.custody_mode,
        "inputs_digest": digest_bytes(canonical_json([])),
        "execution_profile_digest": digest_bytes(canonical_json({})),
        "delta_safe": True,
        "delta_digest": digest_bytes(b""),
        "delta_bytes": 0,
        "workspace_clean": True,
        "sandbox_image": SANDBOX_IMAGE,
        "sandbox_profile_digest": SANDBOX_PROFILE_DIGEST,
        "sandbox_attestation_digest": digest_text("limen-sandbox-boundary-v1\n"),
        "outputs": [output_for(req, observed).identity()],
    }
    payload["receipt_digest"] = digest_bytes(canonical_json(payload))
    return payload


@pytest.mark.parametrize(
    "field",
    [
        "request_id",
        "provider",
        "task_id",
        "repo",
        "base_sha",
        "observed_sha",
        "control_repo",
        "control_ref",
        "control_ref_kind",
        "control_sha",
        "observed_control_sha",
        "observed_control_ref",
        "observed_control_ref_kind",
        "workflow_id",
        "workflow_path",
        "observed_workflow_path",
        "workflow_event",
        "observed_workflow_event",
        "observed_workflow_sha",
        "verification_context_digest",
        "predicate_digest",
        "instruction_digest",
        "packet_digest",
        "receipt_target",
        "custody_mode",
        "inputs_digest",
        "execution_profile_digest",
        "delta_safe",
        "delta_digest",
        "delta_bytes",
        "workspace_clean",
        "sandbox_image",
        "sandbox_profile_digest",
        "sandbox_attestation_digest",
    ],
)
def test_workflow_receipt_binds_every_packet_field(field: str) -> None:
    req = request()
    observed = run(req, RemoteState.SUCCEEDED)
    payload = workflow_payload(req, observed)
    payload[field] = False if isinstance(payload[field], bool) else "tampered"
    payload.pop("receipt_digest")
    payload["receipt_digest"] = digest_bytes(canonical_json(payload))
    with pytest.raises(RemoteExecutionError, match=field):
        _receipt_from_workflow_payload(payload, req, observed, "organvm/limen")


def test_workflow_receipt_digest_is_verified_before_fields() -> None:
    req = request()
    observed = run(req, RemoteState.SUCCEEDED)
    payload = workflow_payload(req, observed)
    payload["receipt_digest"] = DIGEST
    with pytest.raises(RemoteExecutionError, match="receipt digest mismatch"):
        _receipt_from_workflow_payload(payload, req, observed, "organvm/limen")


def _task(req: RemoteRequest, observed: RemoteRun, receipt_path: str) -> Task:
    return verification_task(
        req.task_id,
        status="dispatched",
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime.fromisoformat(observed.observed_at),
                agent=req.provider,
                session_id=observed.provider_run_id,
                status="dispatched",
                provider_run_id=observed.provider_run_id,
                provider_url=observed.url,
                base_sha=observed.base_sha,
                control_repo=observed.control_repo,
                control_ref=observed.control_ref,
                control_ref_kind=observed.control_ref_kind,
                control_sha=observed.control_sha,
                workflow_id=observed.workflow_id,
                workflow_path=observed.workflow_path,
                workflow_event=observed.workflow_event,
                verification_context_digest=observed.verification_context_digest,
                remote_state=observed.state.value,
                remote_request_id=observed.request_id,
                remote_receipt=receipt_path,
            )
        ],
    )


def _harvest_request() -> RemoteRequest:
    template = verification_task()
    return request(execution_profile=execution_profile_for(template).as_dict())


def harvest_board(task: Task) -> LimenFile:
    return LimenFile(tasks=[implementation_parent(), task])


def test_remote_harvest_is_idempotent_when_provider_state_does_not_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _harvest_request()
    observed = run(req)
    store = ReceiptStore(tmp_path / "logs" / "remote-execution")
    path = store.write(
        RemoteReceipt(req, observed, observed.state, observed_at=observed.observed_at, detail=observed.detail)
    )
    task = _task(req, observed, str(path.relative_to(tmp_path)))
    board = harvest_board(task)
    adapter = StableAdapter(req)
    monkeypatch.setattr("limen.harvest.discover_adapters", lambda: ({req.provider: adapter}, []))

    first = check_remote_harvest(board, tmp_path / "tasks.yaml")
    log_count = len(task.dispatch_log)
    second = check_remote_harvest(board, tmp_path / "tasks.yaml")

    assert first == [req.task_id]
    assert second == []
    assert len(task.dispatch_log) == log_count
    assert task.status == "in_progress"


def test_remote_harvest_adopts_intent_after_crash_before_board_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _harvest_request()
    pending = run(
        req,
        RemoteState.SUBMITTED,
        run_id=f"pending:{req.request_id}",
        detail="submission intent persisted before provider mutation",
    )
    store = ReceiptStore(tmp_path / "logs" / "remote-execution")
    store.write(RemoteReceipt(req, pending, pending.state, observed_at=pending.observed_at, detail=pending.detail))
    task = verification_task(
        req.task_id,
        status="in_progress",
    )
    board = harvest_board(task)
    adapter = StableAdapter(req)
    monkeypatch.setattr("limen.harvest.discover_adapters", lambda: ({req.provider: adapter}, []))

    assert check_remote_harvest(board, tmp_path / "tasks.yaml") == [req.task_id]
    assert task.status == "in_progress"
    assert task.dispatch_log[-1].remote_request_id == req.request_id
    assert task.dispatch_log[-1].provider_run_id == pending.provider_run_id


def test_remote_harvest_routes_missing_adapter_to_named_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _harvest_request()
    observed = run(req)
    task = _task(req, observed, "logs/remote-execution/missing.json")
    board = harvest_board(task)
    monkeypatch.setattr("limen.harvest.discover_adapters", lambda: ({}, []))

    assert check_remote_harvest(board, tmp_path / "tasks.yaml") == [req.task_id]
    assert task.status == "failed_blocked"
    assert "adapter/workflow unavailable" in (task.dispatch_log[-1].output or "")


def test_remote_harvest_never_searches_back_to_superseded_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _harvest_request()
    observed = run(req, RemoteState.SUCCEEDED)
    task = _task(req, observed, "logs/remote-execution/old.json")
    task.status = "in_progress"
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=datetime.now(timezone.utc),
            agent="codex",
            session_id="newer-local-attempt",
            status="in_progress",
        )
    )
    board = harvest_board(task)
    monkeypatch.setattr("limen.harvest.discover_adapters", lambda: ({req.provider: StableAdapter(req)}, []))

    assert check_remote_harvest(board, tmp_path / "tasks.yaml") == []
    assert task.status == "in_progress"
    assert task.dispatch_log[-1].session_id == "newer-local-attempt"


def test_remote_harvest_confirms_old_unmaterialized_attempt_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _harvest_request()
    observed = run(
        req,
        RemoteState.SUBMITTED,
        run_id=f"pending:{req.request_id}",
        detail="pending",
        observed_at=(datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
    )
    store = ReceiptStore(tmp_path / "logs" / "remote-execution")
    path = store.write(
        RemoteReceipt(req, observed, observed.state, observed_at=observed.observed_at, detail=observed.detail)
    )
    task = _task(req, observed, str(path.relative_to(tmp_path)))
    board = harvest_board(task)
    adapter = StableAdapter(req)
    adapter.probe = lambda _request, current: current  # type: ignore[method-assign]
    monkeypatch.setattr("limen.harvest.discover_adapters", lambda: ({req.provider: adapter}, []))

    assert check_remote_harvest(board, tmp_path / "tasks.yaml") == [req.task_id]
    assert task.status == "failed"
    assert task.dispatch_log[-1].remote_state == RemoteState.ABSENT.value


def test_remote_harvest_never_false_dones_task_changed_to_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = _harvest_request()
    observed = run(req, RemoteState.SUCCEEDED)
    store = ReceiptStore(tmp_path / "logs" / "remote-execution")
    path = store.write(RemoteReceipt(req, observed, observed.state, observed_at=observed.observed_at))
    task = _task(req, observed, str(path.relative_to(tmp_path)))
    task.type = "code"
    board = harvest_board(task)
    adapter = StableAdapter(req)
    adapter.harvest = lambda _request, current: successful_receipt(req, current)  # type: ignore[method-assign]
    monkeypatch.setattr("limen.harvest.discover_adapters", lambda: ({req.provider: adapter}, []))

    assert check_remote_harvest(board, tmp_path / "tasks.yaml") == [req.task_id]
    assert task.status == "failed_blocked"
    assert "verification-only" in (task.dispatch_log[-1].output or "")


def test_github_actions_route_and_targeted_dispatch_reject_code_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import dispatch

    task = verification_task(type="code")
    board = harvest_board(task)
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, board)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setattr(
        dispatch,
        "discover_adapters",
        lambda: (_ for _ in ()).throw(AssertionError("verification gate must run before provider discovery")),
    )

    assert not dispatch.agent_can_run_task("github_actions", task)
    result = dispatch._call_remote_adapter("github_actions", task, dry_run=False)
    assert isinstance(result, str)
    assert "verification-only" in result


def test_authoritative_workstream_contract_drift_blocks_before_provider_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import dispatch

    submitted = verification_task(workstream_contract=packet_contract("2d", now_epoch=1_000))
    authoritative = verification_task(workstream_contract=packet_contract("2d", now_epoch=1_001))
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, harvest_board(authoritative))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setattr(
        dispatch,
        "discover_adapters",
        lambda: (_ for _ in ()).throw(AssertionError("contract drift must stop before provider discovery")),
    )

    result = dispatch._call_remote_adapter("github_actions", submitted, dry_run=False)

    assert isinstance(result, str)
    assert dispatch._is_workstream_successor_result(result)
    assert "packet contract changed" in dispatch._workstream_successor_reason(result)


def test_remote_dispatch_final_guard_validates_authoritative_task_before_workflow_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import dispatch

    submitted = verification_task(workstream_contract=packet_contract("2d"))
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, harvest_board(submitted))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    calls: list[tuple[str, ...]] = []
    control_probes = 0
    board_mutated = False

    def runner(argv: object, _timeout: int) -> CommandResult:
        nonlocal board_mutated, control_probes
        args = tuple(argv)  # type: ignore[arg-type]
        calls.append(args)
        if result := preflight_result(args):
            if "/git/ref/heads/main" in " ".join(args):
                control_probes += 1
                if control_probes == 2:
                    parent = implementation_parent()
                    parent.dispatch_log[-1].timestamp = datetime.fromisoformat("2026-07-14T00:00:00+00:00")
                    save_limen_file(tasks_path, LimenFile(tasks=[parent, submitted]))
                    board_mutated = True
            return result
        if args[1:3] == ("workflow", "run"):
            raise AssertionError("drifted workstream must not mutate GitHub")
        if args[1] == "api":
            return CommandResult(args, 0, '[{"workflow_runs": []}]')
        raise AssertionError(args)

    adapter = _actions_adapter(runner)
    monkeypatch.setattr(dispatch, "discover_adapters", lambda: ({"github_actions": adapter}, []))
    monkeypatch.setattr(dispatch, "resolve_pushed_sha", lambda *_args, **_kwargs: SHA)
    monkeypatch.setattr(dispatch, "_remote_receipt_store", lambda: ReceiptStore(tmp_path / "receipts"))

    result = dispatch._call_remote_adapter("github_actions", submitted, dry_run=False)

    assert dispatch._is_blocked_result(result)
    assert "remote request changed" in dispatch._blocked_reason(result)
    assert board_mutated is True
    assert control_probes >= 2
    assert not any(args[1:3] == ("workflow", "run") for args in calls)


@pytest.mark.parametrize(
    ("agent", "callee"),
    [("jules", "_call_jules"), ("copilot", "_call_copilot"), ("warp", "_call_warp_oz")],
)
def test_native_remote_lanes_retain_their_guarded_dispatch_paths(
    agent: str,
    callee: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import dispatch

    task = Task(
        id="ROUTE-1",
        title="route",
        repo="organvm/limen",
        target_agent=agent,
        created=date(2026, 7, 13),
    )
    monkeypatch.delenv("LIMEN_DISPATCH_CMD", raising=False)
    called: list[tuple[object, ...]] = []

    def guarded(*args: object) -> str:
        called.append(args)
        return "guarded-path"

    monkeypatch.setattr(dispatch, callee, guarded)
    assert dispatch.call_agent_dispatch(agent, task, dry_run=False) == "guarded-path"
    assert called


def test_github_actions_dispatch_uses_attested_adapter_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from limen import dispatch

    task = verification_task("ROUTE-GHA")
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", "must-not-bypass-attested-route")
    monkeypatch.setattr(
        dispatch,
        "_run_cmd",
        lambda *args: (_ for _ in ()).throw(AssertionError("override bypassed attested route")),
    )
    monkeypatch.setattr(dispatch, "_call_remote_adapter", lambda *args: "attested-path")
    assert dispatch.call_agent_dispatch("github_actions", task, dry_run=False) == "attested-path"


def test_dispatch_result_persists_remote_attempt_identity() -> None:
    from limen import dispatch

    task = verification_task("ROUTE-GHA")
    req = request(task_id=task.id, receipt_target=f"artifact:organvm/limen:task:{task.id}")
    observed = run(req)
    dispatch._REMOTE_SUBMISSION_RECEIPTS[task.id] = {
        "provider_run_id": observed.provider_run_id,
        "provider_url": observed.url,
        "base_sha": observed.base_sha,
        "control_repo": observed.control_repo,
        "control_ref": observed.control_ref,
        "control_ref_kind": observed.control_ref_kind,
        "control_sha": observed.control_sha,
        "workflow_id": observed.workflow_id,
        "workflow_path": observed.workflow_path,
        "workflow_event": observed.workflow_event,
        "verification_context_digest": observed.verification_context_digest,
        "remote_state": observed.state.value,
        "remote_request_id": observed.request_id,
        "remote_receipt": "logs/remote-execution/receipt.json",
    }
    try:
        dispatch._apply_result(
            task,
            "github_actions",
            observed.provider_run_id,
            datetime.now(timezone.utc),
            BudgetTrack(date="2026-07-13"),
        )
    finally:
        dispatch._REMOTE_SUBMISSION_RECEIPTS.pop(task.id, None)
    assert task.dispatch_log[-1].remote_request_id == observed.request_id
    assert task.dispatch_log[-1].provider_url == observed.url
    assert task.dispatch_log[-1].control_ref == observed.control_ref
    assert task.dispatch_log[-1].control_ref_kind == observed.control_ref_kind
    assert task.dispatch_log[-1].control_sha == observed.control_sha
    assert task.dispatch_log[-1].workflow_id == observed.workflow_id


def test_workflow_has_no_raw_shell_predicate_or_patch_upload() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "limen-agent.yml").read_text()
    assert "bash -lc" not in workflow
    assert "remote.patch" not in workflow
    assert "actions/checkout@v" not in workflow
    assert "actions/upload-artifact@v" not in workflow
    assert "persist-credentials: false" in workflow
    assert "remote_predicate.py" in workflow
    assert "inputs.base_sha" in workflow
    assert "inputs.control_ref" in workflow
    assert "inputs.control_ref_kind" in workflow
    assert "inputs.control_sha" in workflow
    assert "inputs.workflow_id" in workflow
    assert "github.workflow_sha" in workflow
    assert "LIMEN_OBSERVED_WORKFLOW_REF: ${{ github.workflow_ref }}" in workflow
    assert "github.ref_name" in workflow
    assert "github.ref_type" in workflow
    assert "inputs.workflow_path" in workflow
    assert "verification_context_digest" in workflow
    assert 'docker pull "$LIMEN_SANDBOX_IMAGE"' in workflow
    assert SANDBOX_IMAGE in workflow
    assert "instruction_digest" in workflow
