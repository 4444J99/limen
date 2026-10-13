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
