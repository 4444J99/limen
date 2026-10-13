"""Behavioral regressions for the keeper's immutable remote execution deadline."""

from datetime import datetime, timedelta, timezone

import pytest

from test_remote_execution import request


def test_request_deadline_change_changes_attempt_identity():
    first = request(attempt_deadline="2099-01-01T00:10:00+00:00", verification_deadline="2099-01-01T00:05:00+00:00")
    second = request(attempt_deadline="2099-01-01T00:10:00+00:00", verification_deadline="2099-01-01T00:04:00+00:00")
    assert first.request_id != second.request_id
    assert first.public_manifest()["verification_deadline"] == "2099-01-01T00:05:00+00:00"


def test_expired_request_is_rejected_before_any_provider_read():
    from limen.remote_execution import GitHubWorkflowAdapter, RemoteExecutionError
    from test_remote_execution import CONTROL_SHA, WORKFLOW_ID

    expired = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    req = request(attempt_deadline=expired, verification_deadline=expired)

    def must_not_contact_provider(*args):
        pytest.fail("expired request contacted provider")

    adapter = GitHubWorkflowAdapter(
        provider=req.provider,
        control_repo=req.control_repo,
        control_sha=CONTROL_SHA,
        control_ref=req.control_ref,
        control_ref_kind=req.control_ref_kind,
        workflow_path=req.workflow_path,
        workflow_id=WORKFLOW_ID,
        runner=must_not_contact_provider,
    )
    with pytest.raises(RemoteExecutionError, match="deadline|expired"):
        adapter.preflight(req)


def test_verification_deadline_cannot_outlive_attempt():
    with pytest.raises(ValueError, match="deadline"):
        request(attempt_deadline="2099-01-01T00:05:00+00:00", verification_deadline="2099-01-01T00:10:00+00:00")


def test_worker_rejects_queued_expiry_before_git_or_sandbox(tmp_path):
    from limen.remote_predicate import PredicateContractError, execute_attested
    from test_remote_execution import _worker_args

    expired = "2000-01-01T00:00:00+00:00"
    req = request(attempt_deadline=expired, verification_deadline=expired)
    args = _worker_args(tmp_path, req)
    args.attempt_deadline = expired
    args.verification_deadline = expired
    with pytest.raises(PredicateContractError, match="deadline expired"):
        execute_attested(args)


def test_sandbox_timeout_removes_the_owned_container(tmp_path):
    import subprocess
    import sys
    from limen.remote_predicate import _default_sandbox_runner

    marker = tmp_path / "container"
    marker.write_text("limen-verifier-" + "a" * 32)
    docker = tmp_path / "docker-fixture"
    docker.write_text(
        f"#!{sys.executable}\nimport pathlib, sys, time\n"
        f"p = pathlib.Path({str(marker)!r})\n"
        "if sys.argv[1] == 'run':\n p.write_text(sys.argv[3]); time.sleep(10)\n"
        "elif sys.argv[1:3] == ['rm', '--force']:\n"
        " assert p.read_text() == sys.argv[3]; p.unlink()\n"
        "else:\n raise SystemExit(1)\n"
    )
    docker.chmod(0o700)
    result = _default_sandbox_runner((str(docker), "run", "--name", "limen-verifier-" + "a" * 32), 1)
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 124
    assert not marker.exists(), "Docker CLI timeout left its container running"


def test_receipt_deadlines_cannot_be_changed_even_with_recomputed_digest():
    from limen.remote_execution import RemoteExecutionError, RemoteState, _receipt_from_workflow_payload
    from limen.remote_predicate import canonical_json, digest_bytes
    from test_remote_execution import run, workflow_payload

    req = request()
    observed = run(req, RemoteState.SUCCEEDED)
    payload = workflow_payload(req, observed)
    payload["verification_deadline"] = "2099-01-01T00:04:00+00:00"
    payload.pop("receipt_digest")
    payload["receipt_digest"] = digest_bytes(canonical_json(payload))
    with pytest.raises(RemoteExecutionError, match="verification_deadline"):
        _receipt_from_workflow_payload(payload, req, observed, req.control_repo)


def test_historical_receipt_keeps_original_deadline_and_request_identity(tmp_path):
    from limen.remote_execution import ReceiptStore, RemoteState, load_receipt
    from test_remote_execution import run, successful_receipt

    req = request()
    store = ReceiptStore(tmp_path)
    path = store.write(successful_receipt(req, run(req, RemoteState.SUCCEEDED)))
    recovered = load_receipt(path, req)
    assert recovered.request.request_id == req.request_id
    assert recovered.request.verification_deadline == "2099-01-01T00:05:00+00:00"


@pytest.mark.parametrize(
    "started,completed",
    [
        (None, None),
        ("2099-01-01T00:01:00+00:00", "2099-01-01T00:06:00+00:00"),
        ("2099-01-01T00:03:00+00:00", "2099-01-01T00:02:00+00:00"),
    ],
)
def test_new_receipt_requires_ordered_bounded_execution_timing(started, completed):
    from limen.remote_execution import RemoteExecutionError, RemoteState, _receipt_from_workflow_payload
    from limen.remote_predicate import canonical_json, digest_bytes
    from test_remote_execution import run, workflow_payload

    req = request()
    observed = run(req, RemoteState.SUCCEEDED)
    payload = workflow_payload(req, observed)
    payload["started_at"] = started
    payload["completed_at"] = completed
    payload.pop("receipt_digest")
    payload["receipt_digest"] = digest_bytes(canonical_json(payload))
    with pytest.raises(RemoteExecutionError, match="timing"):
        _receipt_from_workflow_payload(payload, req, observed, req.control_repo)


def test_git_preparation_rejects_expiry_without_starting_process(tmp_path):
    from limen.remote_predicate import PredicateContractError, _git

    with pytest.raises(PredicateContractError, match="expired"):
        _git(tmp_path, "rev-parse", "HEAD", deadlines=("2000-01-01T00:00:00Z", "2000-01-01T00:00:00Z"))


def test_legacy_workflow_receipt_without_deadline_evidence_still_reads():
    from limen.remote_execution import RemoteState, _receipt_from_workflow_payload
    from limen.remote_predicate import canonical_json, digest_bytes
    from test_remote_execution import run, workflow_payload

    req = request(attempt_deadline=None, verification_deadline=None)
    observed = run(req, RemoteState.SUCCEEDED)
    payload = workflow_payload(req, observed)
    for key in ("attempt_deadline", "verification_deadline", "started_at", "completed_at", "receipt_digest"):
        payload.pop(key, None)
    payload["receipt_digest"] = digest_bytes(canonical_json(payload))
    assert _receipt_from_workflow_payload(payload, req, observed, req.control_repo).state == RemoteState.SUCCEEDED


def test_workflow_preparation_is_killed_at_original_deadline(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    import yaml

    workflow = yaml.safe_load((Path(__file__).parents[2] / ".github/workflows/limen-agent.yml").read_text())
    bootstrap = workflow["jobs"]["deterministic-compute"]["steps"][0]["run"]
    marker = tmp_path / "git-started"
    git = tmp_path / "git"
    git.write_text(f"#!{sys.executable}\nimport pathlib, time\npathlib.Path({str(marker)!r}).touch()\ntime.sleep(30)\n")
    git.chmod(0o700)
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
    environment = dict(
        os.environ,
        PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
        LIMEN_ATTEMPT_DEADLINE=deadline,
        VERIFICATION_DEADLINE=deadline,
        LIMEN_CONTROL_REPO="4444J99/limen",
        LIMEN_CONTROL_SHA="a" * 40,
        LIMEN_TARGET_REPO="4444J99/limen",
        LIMEN_BASE_SHA="b" * 40,
        LIMEN_REQUEST_ID="c" * 32,
    )
    result = subprocess.run(
        [sys.executable, "-c", bootstrap], cwd=tmp_path, env=environment, capture_output=True, timeout=6
    )
    assert marker.exists(), "workflow did not execute its checkout preparation under the deadline"
    assert result.returncode != 0, "preparation continued beyond its original reservation"


def test_journal_admits_only_actions_verification_with_keeper_bounds(monkeypatch, tmp_path, admitted_local_execution):
    import limen.dispatch as dispatch
    from limen.models import Task
    from test_work_loan_journal import task_row, store, journal_snapshots

    task = Task.model_validate(
        task_row(
            "DEADLINE-ADMISSION", type="verification", target_agent="github_actions", labels=["mode:verification-only"]
        )
    )
    admitted_local_execution(dispatch, task.id)
    journal = store(tmp_path)
    monkeypatch.setattr(dispatch, "default_work_loan_journal_store", lambda: journal)
    monkeypatch.setattr(dispatch, "call_agent_dispatch", lambda *_a, **_kw: "hosted-run-1")
    assert dispatch._journaled_agent_dispatch("github_actions", task, False, "reservation-1") == "hosted-run-1"
    assert journal_snapshots(journal.read())[0]["actual"]["runs"] == 1

    # The extension must not admit another provider or an implementation task.
    assert dispatch._is_prelaunch_result(dispatch._journaled_agent_dispatch("jules", task, False, "reservation-2"))
    task.type = "code"
    assert dispatch._is_prelaunch_result(
        dispatch._journaled_agent_dispatch("github_actions", task, False, "reservation-3")
    )


def test_generated_boundary_probe_is_readable_by_unprivileged_container():
    import subprocess
    from pathlib import Path
    from limen.remote_predicate import _attest_sandbox, SANDBOX_OK

    def filesystem_boundary(argv, timeout):
        mount = argv[argv.index("--mount") + 1]
        root = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
        # The real container runs as 65534, not the trusted host owner's UID.
        readable = root.stat().st_mode & 0o005 == 0o005
        return subprocess.CompletedProcess(argv, 0 if readable else 1, SANDBOX_OK if readable else b"permission denied")

    _attest_sandbox(filesystem_boundary, docker_binary="docker-fixture", timeout=30)
