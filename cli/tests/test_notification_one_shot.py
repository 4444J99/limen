"""Tests for the bounded processless notification one-shot."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.conduct import ConductBroker, ConductPrincipalV1, MemoryStateStore


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "notification-one-shot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("notification_one_shot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state_paths(module, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(module, "RECEIPT", tmp_path / "notification-one-shot.json")
    monkeypatch.setattr(module, "LOCK", tmp_path / "notification-one-shot.lock")
    monkeypatch.setattr(module, "FAILURE_STATE", tmp_path / "notification-one-shot-failures.json")


def _broker_edge(module, monkeypatch):
    """Keep the production HTTP client, replacing only its authenticated remote edge."""
    broker = ConductBroker(MemoryStateStore())
    principal = ConductPrincipalV1(
        principal_id="notification-test-principal",
        agent="codex",
        surface="cli",
        roles=frozenset({"observer", "conductor", "executor"}),
    )
    identity = module.AgentIdentityV1(agent="codex", surface="cli", session_id="notification-test-session")
    broker.register(
        module.ConductorSessionV1(
            session_id=identity.session_id,
            identity=identity,
            origin="relay",
            capabilities=frozenset({"execute", "conduct", "notification-one-shot"}),
        ),
        principal=principal,
    )
    calls = []

    def request(client, method, path, payload=None):
        assert client.token == "notification-test-credential"  # allow-secret: fabricated fixture credential
        assert client.timeout == module.CONDUCT_TIMEOUT_SECONDS
        calls.append((method, path))
        if path == "/api/conduct/capabilities":
            return broker.capabilities(principal=principal)
        if path == "/api/conduct/sessions":
            return broker.register(module.ConductorSessionV1.model_validate(payload), principal=principal)
        if path == "/api/conduct/runs":
            return broker.submit(module.WorkPacketV1.model_validate(payload), principal=principal)
        if path.endswith("/graph"):
            return broker.graph(path.split("/")[-2], principal=principal)
        if path.endswith("/claim"):
            return broker.claim(path.split("/")[-2], payload["generation"], principal=principal)
        if path.endswith("/heartbeat"):
            return broker.heartbeat(
                path.split("/")[-2], payload["capability_token"], generation=payload["generation"], principal=principal
            )
        if path.endswith("/receipt"):
            return broker.report(
                path.split("/")[-2],
                payload["capability_token"],
                module.RunReceiptV1.model_validate(payload["receipt"]),
                generation=payload["generation"],
                principal=principal,
            )
        if path.endswith("/cancel"):
            return broker.cancel(path.split("/")[-2], payload["session_id"], principal=principal)
        raise AssertionError(f"unexpected broker edge: {method} {path}")

    monkeypatch.setattr(module.HttpConductClient, "_request", request)
    monkeypatch.setenv("LIMEN_CONDUCT_URL", "https://conduct.test.invalid")
    monkeypatch.setenv("LIMEN_CONDUCT_TOKEN", "notification-test-credential")
    monkeypatch.setenv("LIMEN_SESSION_ID", identity.session_id)
    return broker, principal, calls


def test_default_invocation_is_plan_only(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("producer invoked")),
    )

    assert module.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["apply_required"] is True
    assert not module.STATE_ROOT.exists()


def test_apply_fails_when_a_producer_exits_zero_without_complete_evidence(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_steps", lambda: [("ships-24h", ["python", str(SCRIPT)], 1)])
    broker, principal, _calls = _broker_edge(module, monkeypatch)
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: {
            "name": "ships-24h",
            "returncode": 0,
            "producer_complete": False,
            "timed_out": False,
        },
    )

    assert module.main(["--apply", "--fresh-lease"]) == 1
    receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["consecutive_failures"] == 1
    run = broker.graph(receipt["execution_lease"]["run_id"], principal=principal)["nodes"][0]
    assert run["status"] == "failed"
    assert run["lease"]["state"] == "released"


def test_consecutive_failure_kill_switch_prevents_producer_execution(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    module.FAILURE_STATE.write_text(
        json.dumps({"consecutive_failures": module.MAX_CONSECUTIVE_FAILURES}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("producer invoked")),
    )

    assert module.main(["--apply"]) == 78


def test_shipping_producer_requires_fresh_complete_cache(tmp_path, monkeypatch):
    module = _load_module()
    live = tmp_path / "live"
    cache = live / "logs" / "ships-24h.json"
    cache.parent.mkdir(parents=True)
    monkeypatch.setattr(module, "LIVE_ROOT", live)
    cache.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "complete": False,
                "error": "partial-owner-query",
            }
        ),
        encoding="utf-8",
    )

    assert module._producer_complete("ships-24h", 0) is False
    payload = json.loads(cache.read_text(encoding="utf-8"))
    payload.update({"complete": True, "error": None})
    cache.write_text(json.dumps(payload), encoding="utf-8")
    assert module._producer_complete("ships-24h", 0) is True


@pytest.mark.parametrize("extra", [[], ["--fresh-lease"], ["--reset-failures"]])
def test_apply_requires_authenticated_broker_before_effects(tmp_path, monkeypatch, extra):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    monkeypatch.delenv("LIMEN_CONDUCT_URL", raising=False)
    monkeypatch.delenv("LIMEN_CONDUCT_TOKEN", raising=False)
    monkeypatch.setenv("LIMEN_CONDUCT_STATE", str(tmp_path / "development-only.sqlite"))
    monkeypatch.setattr(module, "_run_step", lambda *_args: pytest.fail("producer executed without owning contract"))

    assert module.main(["--apply", *extra]) == 77
    assert not module.STATE_ROOT.exists()
    assert not (tmp_path / "development-only.sqlite").exists()


def test_fresh_lease_dry_run_has_no_broker_or_producer_effect(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    monkeypatch.setattr(module, "_conduct_client", lambda *_args: pytest.fail("broker invoked in dry-run"))

    assert module.main(["--apply", "--fresh-lease", "--dry-run"]) == 0
    assert not module.STATE_ROOT.exists()


def test_fresh_run_is_reported_and_local_lock_is_not_its_lease(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_steps", lambda: [("events", ["python", str(SCRIPT)], 1)])
    broker, principal, calls = _broker_edge(module, monkeypatch)
    monkeypatch.setattr(
        module, "_run_step", lambda *_args: {"name": "events", "returncode": 0, "producer_complete": True}
    )

    assert module.main(["--apply", "--fresh-lease"]) == 0
    receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
    lease = receipt["execution_lease"]
    assert lease["run_id"].startswith("run-")
    assert receipt["local_overlap_guard"] == "exclusive-flock"
    run = broker.graph(lease["run_id"], principal=principal)["nodes"][0]
    assert run["status"] == "succeeded"
    assert run["lease"]["state"] == "released"
    assert sum(path.endswith("/heartbeat") for _method, path in calls) >= 3
    assert "notification-test-credential" not in capsys.readouterr().out
    assert "capability_token" not in module.RECEIPT.read_text(encoding="utf-8")


def test_wrong_executor_cannot_reuse_an_existing_lease(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    _broker_edge(module, monkeypatch)
    environment = dict(module.os.environ)
    contract = module._fresh_contract(module._conduct_client(environment), environment)
    environment["LIMEN_SESSION_ID"] = "other-executor"
    with pytest.raises(ValueError, match="not owned"):
        module.ExecutionContract(contract.client, environment)
    assert not module.STATE_ROOT.exists()


def test_changed_producer_plan_cannot_reuse_an_existing_lease(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    _broker_edge(module, monkeypatch)
    environment = dict(module.os.environ)
    contract = module._fresh_contract(module._conduct_client(environment), environment)
    monkeypatch.setattr(module, "LIVE_ROOT", tmp_path / "different-live-root")
    with pytest.raises(ValueError, match="exact notification producer plan"):
        module.ExecutionContract(contract.client, environment)
    assert not module.STATE_ROOT.exists()


def test_lost_lease_stops_before_the_next_producer(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    monkeypatch.setattr(
        module, "_steps", lambda: [("first", ["python", str(SCRIPT)], 1), ("second", ["python", str(SCRIPT)], 1)]
    )
    broker, principal, _calls = _broker_edge(module, monkeypatch)
    executed = []

    def producer(name, _command, _timeout, environment):
        executed.append(name)
        # A real terminal broker transition fences subsequent heartbeats.
        environment_copy = dict(environment)
        contract = module.ExecutionContract(module._conduct_client(environment_copy), environment_copy)
        module._report_contract(contract, 1)
        return {"name": name, "returncode": 0, "producer_complete": True}

    monkeypatch.setattr(module, "_run_step", producer)
    assert module.main(["--apply", "--fresh-lease"]) != 0
    assert executed == ["first"]
    receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
    assert receipt["status"] != "complete"


def test_private_environment_cache_is_read_without_running_shell(tmp_path):
    module = _load_module()
    cache = tmp_path / "conduct.env"
    cache.write_text(
        "export LIMEN_CONDUCT_URL='https://conduct.test.invalid'\nexport LIMEN_CONDUCT_TOKEN='test-only-token'\n",
        encoding="utf-8",
    )
    cache.chmod(0o600)
    environment = {}
    module._hydrate_conduct_environment(environment, cache)
    assert environment["LIMEN_CONDUCT_URL"] == "https://conduct.test.invalid"
    cache.write_text("export LIMEN_CONDUCT_TOKEN=$(touch forbidden)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="literal assignments"):
        module._hydrate_conduct_environment({}, cache)
    cache.chmod(0o644)
    with pytest.raises(ValueError, match="mode-600"):
        module._hydrate_conduct_environment({}, cache)


def test_report_executes_exact_work_predicate_instead_of_trusting_operation_exit(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    broker, principal, _calls = _broker_edge(module, monkeypatch)
    environment = dict(module.os.environ)
    contract = module._fresh_contract(module._conduct_client(environment), environment)
    contract.heartbeat()
    module.RECEIPT.write_text(
        json.dumps({"status": "complete", "work_id": "an-older-run", "operation": "produce"}), encoding="utf-8"
    )

    assert module._report_contract(contract, 0) == 1
    run = broker.graph(contract.run_id, principal=principal)["nodes"][0]
    assert run["status"] == "failed"
    assert run["receipts"][-1]["predicate"]["exit_code"] == 1
    assert contract.packet.work_id in run["receipts"][-1]["predicate"]["command"]


def test_reset_has_its_own_receipt_and_verified_predicate(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    broker, principal, _calls = _broker_edge(module, monkeypatch)
    module.FAILURE_STATE.write_text(
        json.dumps({"consecutive_failures": module.MAX_CONSECUTIVE_FAILURES}), encoding="utf-8"
    )
    monkeypatch.setattr(module, "_run_step", lambda *_args: pytest.fail("reset ran a producer"))

    assert module.main(["--apply", "--fresh-lease", "--reset-failures"]) == 0
    receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
    assert receipt["operation"] == "reset-failures"
    assert receipt["steps"] == []
    assert receipt["consecutive_failures"] == 0
    run = broker.graph(receipt["execution_lease"]["run_id"], principal=principal)["nodes"][0]
    assert run["status"] == "succeeded"
    assert "reset-failures" in run["packet"]["predicate"]
    assert run["receipts"][-1]["predicate"]["exit_code"] == 0
    assert module._status(receipt["work_id"], "produce") == 1


def test_producer_replacement_after_packet_acceptance_is_refused(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    source = tmp_path / "producer.py"
    source.write_text("print('original')\n", encoding="utf-8")
    monkeypatch.setattr(module, "_steps", lambda: [("events", [module.sys.executable, str(source)], 1)])
    _broker, _principal, calls = _broker_edge(module, monkeypatch)
    environment = dict(module.os.environ)
    contract = module._fresh_contract(module._conduct_client(environment), environment)
    call_count = len(calls)
    source.write_text("print('replacement')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sources changed"):
        contract.heartbeat(1)
    assert len(calls) == call_count
    assert not module.STATE_ROOT.exists()
