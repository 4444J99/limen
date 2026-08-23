import json
from pathlib import Path

from limen import observer
from limen.bounded_subprocess import BoundedCompletedProcess, BoundedSubprocessError


def test_observer_writes_counts_only_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(
        observer,
        "_run",
        lambda *args, **kwargs: {"status": "passed", "returncode": 0, "duration_ms": 1, "output_bytes": 3},
    )
    monkeypatch.setattr(observer, "_boot_identity", lambda: "boot")
    monkeypatch.setenv("LIMEN_OBSERVE_RECEIPT", str(tmp_path / "receipt.json"))
    receipt = observer.observe_once(tmp_path, "all")
    assert receipt["counts"] == {"passed": receipt["probe_count"], "failed": 0, "timed_out": 0}
    assert "results" not in receipt
    assert json.loads((tmp_path / "receipt.json").read_text()) == receipt


def test_observer_declares_no_mutating_probe():
    source = Path(observer.__file__).read_text()
    for forbidden in ("dispatch --", "--apply", "rerun", "sync-release"):
        assert forbidden not in source


def test_host_observer_executes_every_host_owned_rung():
    ownership = json.loads(
        (Path(__file__).resolve().parents[2] / "institutio/governance/heartbeat-ownership.json").read_text()
    )["rungs"]
    expected = {name for name, row in ownership.items() if row["owner"] == "observe_host"}
    assert expected <= {name for name, _command, _timeout in observer.HOST_PROBES}


def test_remote_observer_executes_every_remote_owned_rung():
    ownership = json.loads(
        (Path(__file__).resolve().parents[2] / "institutio/governance/heartbeat-ownership.json").read_text()
    )["rungs"]
    expected = {name for name, row in ownership.items() if row["owner"] == "observe_remote"}
    assert expected <= {name for name, _command, _timeout in observer.REMOTE_PROBES}


def test_owned_probe_timeouts_match_registry_and_commands_are_report_only():
    ownership = json.loads(
        (Path(__file__).resolve().parents[2] / "institutio/governance/heartbeat-ownership.json").read_text()
    )["rungs"]
    for name, command, timeout in observer.HOST_PROBES + observer.REMOTE_PROBES:
        if name in ownership and ownership[name]["owner"] in {"observe_host", "observe_remote"}:
            assert timeout == ownership[name]["timeout_seconds"]
        assert not {"--apply", "--emit", "--record", "dispatch"} & set(command)
    commands = {name: command for name, command, _timeout in observer.HOST_PROBES + observer.REMOTE_PROBES}
    assert "--no-write" in commands["github-actions-usage"]


def test_boot_identity_rejects_nonzero_probe(monkeypatch):
    monkeypatch.setattr(
        observer.subprocess,
        "run",
        lambda *_args, **_kwargs: observer.subprocess.CompletedProcess([], 1, "", "unknown oid"),
    )
    assert observer._boot_identity() == "unavailable"


def test_probe_uses_bounded_runner(monkeypatch, tmp_path):
    calls = []

    def bounded(command, **kwargs):
        calls.append((command, kwargs))
        return BoundedCompletedProcess(returncode=0, stdout=b"ok", stderr=b"")

    monkeypatch.setattr(observer, "run_bounded_subprocess", bounded)
    result = observer._run(["probe"], cwd=tmp_path, timeout=7)
    assert result["status"] == "passed"
    assert result["output_bytes"] == 2
    assert calls[0][1]["stdout_ceiling"] == observer.PROBE_STDOUT_CEILING
    assert calls[0][1]["stderr_ceiling"] == observer.PROBE_STDERR_CEILING


def test_probe_reports_output_ceiling_failure(monkeypatch, tmp_path):
    def exceeds(*_args, **_kwargs):
        raise BoundedSubprocessError("output")

    monkeypatch.setattr(observer, "run_bounded_subprocess", exceeds)
    result = observer._run(["probe"], cwd=tmp_path, timeout=7)
    assert result["status"] == "failed"
    assert result["failure_kind"] == "output"
    assert result["output_bytes"] is None


def test_runtime_digest_covers_every_executed_probe(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for _name, command, _timeout in observer.HOST_PROBES:
        for argument in command[1:]:
            if argument.startswith("scripts/"):
                path = tmp_path / argument
                path.write_text("v1", encoding="utf-8")
    monkeypatch.setattr(
        observer,
        "_run",
        lambda *args, **kwargs: {"status": "passed", "returncode": 0, "duration_ms": 1, "output_bytes": 0},
    )
    monkeypatch.setattr(observer, "_boot_identity", lambda: "boot")
    monkeypatch.setenv("LIMEN_OBSERVE_RECEIPT", str(tmp_path / "receipt.json"))
    before = observer.observe_once(tmp_path, "host")["runtime_content_digest"]
    (scripts / "check-notification-registry.py").write_text("v2", encoding="utf-8")
    after = observer.observe_once(tmp_path, "host")["runtime_content_digest"]
    assert before != after
