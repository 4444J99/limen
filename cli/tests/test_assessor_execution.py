"""Real child execution verifies isolation; fault injection checks refusal paths."""

import hashlib
import json
from pathlib import Path

import pytest

from limen.bounded_subprocess import BoundedCompletedProcess, BoundedSubprocessError
from limen.conduct.assessor_execution import AssessorExecutionError, execute_assessor
from limen.conduct.assessor_source import AssessorSnapshot


def snapshot(source):
    data = source.encode()
    return AssessorSnapshot("c" * 40, hashlib.sha256(data).hexdigest(), data)


def invoke(source, **overrides):
    values = dict(
        credential="fixture-explicit",
        repository="organvm/.github",
        repository_id=1154799938,
        run_id=123,
        run_attempt=2,
        head_sha="a" * 40,
    )
    values.update(overrides)
    return execute_assessor(source, **values)


def ready():
    return dict(
        status="REVIEW_READY",
        reason="EXACT_HEAD_ACTIONS_CI",
        automatic_acceptance=False,
        repository_id=1154799938,
        run_id=123,
        run_attempt=2,
        head="a" * 40,
        base_sha="b" * 40,
        pr=22,
    )


def test_real_child_isolated_environment_and_temporary_source_removed(monkeypatch):
    monkeypatch.setenv("LIMEN_CONDUCT_TOKEN", "must-not-inherit")
    monkeypatch.setenv("GH_TOKEN", "must-not-inherit")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    source = snapshot(
        """import json, os, sys
assert sys.flags.isolated
assert os.environ['GH_TOKEN'] == 'fixture-explicit'
assert 'LIMEN_CONDUCT_TOKEN' not in os.environ
assert 'PYTHONPATH' not in os.environ
assert '--expected-attempt' in sys.argv
print(json.dumps(%r))
"""
        % ready()
    )
    from limen.conduct import assessor_execution as module

    original = module.run_bounded_subprocess
    locations = []

    def record(command, **kwargs):
        locations.append(Path(command[2]))
        assert kwargs["timeout_seconds"] == 95
        return original(command, **kwargs)

    monkeypatch.setattr(module, "run_bounded_subprocess", record)
    result = invoke(source)
    assert result["status"] == "REVIEW_READY"
    assert result["automatic_acceptance"] is False
    assert result["head_sha"] == "a" * 40
    assert locations and not locations[0].exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", 124),
        ("run_attempt", True),
        ("head", "b" * 40),
        ("repository_id", 42),
        ("automatic_acceptance", True),
        ("base_sha", "invalid"),
    ],
)
def test_wrong_binding_is_unmeasured(monkeypatch, field, value):
    payload = ready()
    payload[field] = value
    monkeypatch.setattr(
        "limen.conduct.assessor_execution.run_bounded_subprocess",
        lambda *a, **kw: BoundedCompletedProcess(0, json.dumps(payload).encode(), b""),
    )
    with pytest.raises(AssessorExecutionError, match="unmeasured"):
        invoke(snapshot("pass"))


def test_hold_is_not_acceptance_and_unknown_fields_are_discarded():
    source = snapshot(
        "import json; print(json.dumps(dict(status='HOLD', reason='AUTHORIZATION', "
        "automatic_acceptance=False, unrelated='discard'))); raise SystemExit(2)"
    )
    result = invoke(source)
    assert result["status"] == "HOLD"
    assert "unrelated" not in result


@pytest.mark.parametrize("output", [b'{"automatic_acceptance":true,"automatic_acceptance":false}', b"[]", b"not json"])
def test_malformed_output_is_redacted(monkeypatch, output):
    monkeypatch.setattr(
        "limen.conduct.assessor_execution.run_bounded_subprocess",
        lambda *a, **kw: BoundedCompletedProcess(0, output, b"sensitive stderr"),
    )
    with pytest.raises(AssessorExecutionError, match="^assessor execution is unmeasured$"):
        invoke(snapshot("pass"))


@pytest.mark.parametrize("kind", ["timeout", "output", "descendants", "unavailable"])
def test_bounded_runner_failures_are_redacted(monkeypatch, kind):
    def fail(*args, **kwargs):
        raise BoundedSubprocessError(kind)

    monkeypatch.setattr("limen.conduct.assessor_execution.run_bounded_subprocess", fail)
    with pytest.raises(AssessorExecutionError, match="^assessor execution is unmeasured$"):
        invoke(snapshot("pass"))


def test_missing_credential_and_modified_snapshot_never_start(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("must not execute")

    monkeypatch.setattr("limen.conduct.assessor_execution.run_bounded_subprocess", forbidden)
    monkeypatch.setenv("GH_TOKEN", "ambient-does-not-authorize")
    with pytest.raises(AssessorExecutionError, match="input is invalid"):
        invoke(snapshot("pass"), credential="")
    with pytest.raises(AssessorExecutionError, match="input is invalid"):
        invoke(AssessorSnapshot("c" * 40, "0" * 64, b"changed"))
