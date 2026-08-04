from __future__ import annotations

from datetime import UTC, datetime

import pytest
from limen.conduct import task_execution
from limen.conduct.client import HttpConductClient, LocalConductClient
from limen.conduct.models import AgentIdentityV1
from limen.conduct.task_execution import (
    TaskExecutionError,
    build_task_execution_packet,
    start_task_execution,
    task_execution_paths,
)
from limen.fanout_executor import CODE_RECEIPT_CAPABILITIES, ProviderLaunch
from limen.models import Task

BASE = "a" * 40
NOW = datetime(2026, 7, 27, 4, 30, tzinfo=UTC)


def _task(**overrides) -> Task:
    payload = {
        "id": "AW-VALUE-REPOS-test",
        "title": "Refresh the product ledger",
        "description": "The current owner receipt is stale.",
        "repo": "organvm/limen",
        "target_agent": "jules",
        "workstream": "revenue-value-repos",
        "budget_cost": 1,
        "status": "open",
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": "Refresh the bounded revenue owner receipt",
        "context": "Run the existing product ledger writer and change only its tracked receipt.",
        "predicate": "python3 scripts/product-ledger.py --write",
        "receipt_target": "git:organvm/limen:docs/product-ledger.md",
        "created": "2026-07-27",
    }
    payload.update(overrides)
    return Task.model_validate(payload)


class FakeAdapter:
    name = "capability-runtime"
    transport = "remote-capability"
    local_heavy = False
    concurrency = 3
    receipt_quality = 0.9
    cost_per_run = 0.0
    quota_remaining = 10.0
    capabilities = CODE_RECEIPT_CAPABILITIES
    conduct_token_env = "LIMEN_CONDUCT_TOKEN_FAKE"
    worker_env_allowlist = frozenset()

    def __init__(self, *, eligible: bool = True):
        self.is_eligible = eligible
        self.launches: list[tuple[str, str]] = []

    def eligible(self, packet):
        return self.is_eligible and packet["execution"]["owner_repository"] == "organvm/limen"

    def launch(self, packet, attempt_id):
        self.launches.append((packet["work_id"], attempt_id))
        return ProviderLaunch("provider-run-1", "https://executor.example/runs/1")

    def recover(self, packet, attempt_id):
        del packet, attempt_id


def test_packet_derives_narrow_authority_and_keeps_target_as_hint():
    task = _task()
    identity = AgentIdentityV1(agent="codex", surface="native", session_id="conductor")

    packet = build_task_execution_packet(
        task,
        conductor=identity,
        executor_session_id="renamed-executor",
        exact_base=BASE,
        deadline=datetime(2026, 7, 27, 8, tzinfo=UTC),
    )

    assert packet.intent["kind"] == "fanout-leaf"
    assert packet.task_id == task.id
    assert packet.preferred_agent == "jules"
    assert packet.execution["executor_session_id"] == "renamed-executor"
    assert packet.execution["observed_heads"] == {"organvm/limen": BASE}
    assert packet.authority.path_prefixes == frozenset({"docs/product-ledger.md"})
    assert packet.required_capabilities == CODE_RECEIPT_CAPABILITIES
    assert any(claim.key.startswith("path/organvm/limen/") for claim in packet.resource_claims)


def test_task_execution_paths_reject_keeper_projection_authority():
    assert task_execution_paths(_task()) == ("docs/product-ledger.md",)
    with pytest.raises(TaskExecutionError, match="tasks.yaml"):
        task_execution_paths(
            _task(
                receipt_target="github:organvm/limen:pull-request:test",
                allowed_paths=["tasks.yaml"],
            )
        )


def test_local_keeper_start_is_reserved_once_and_idempotent(tmp_path, monkeypatch):
    keeper = LocalConductClient(tmp_path / "conduct.sqlite")
    adapter = FakeAdapter()
    monkeypatch.setattr("limen.conduct.broker.utc_now", lambda: NOW)
    monkeypatch.setattr("limen.fanout_executor.remote_default_head", lambda _repo: BASE)

    first = start_task_execution(
        _task(),
        client=keeper,
        execution_adapters=(adapter,),
        exact_base=BASE,
        now=NOW,
    )
    repeated = start_task_execution(
        _task(),
        client=keeper,
        execution_adapters=(adapter,),
        exact_base=BASE,
        now=NOW,
    )

    assert first["status"] == "launched"
    assert first["targeted_launch_count"] == 1
    assert repeated["status"] == "already_running"
    assert repeated["idempotent"] is True
    assert len(adapter.launches) == 1
    graph = keeper.graph(first["root_run_id"])
    node = next(row for row in graph["nodes"] if row["run_id"] == first["run_id"])
    assert node["packet"]["task_id"] == "AW-VALUE-REPOS-test"
    assert node["packet"]["execution"]["exact_base"] == BASE


@pytest.mark.parametrize(
    ("run_status", "expected_status"),
    [("running", "already_running"), ("succeeded", "result_pending_harvest")],
)
def test_active_canonical_task_reuses_broker_run_before_executor_discovery(run_status, expected_status):
    class ExistingRunKeeper:
        def task_run(self, task_id):
            assert task_id == "AW-VALUE-REPOS-test"
            return {
                "schema_version": "limen.conduct_task_run.v1",
                "task_id": task_id,
                "found": True,
                "run_id": "run-existing",
                "root_run_id": "run-existing",
                "status": run_status,
                "executor_session_id": "overnight-jules-remote",
            }

        def register(self, _session):
            raise AssertionError("existing task run must be reused before session registration")

    result = start_task_execution(
        _task(status="dispatched"),
        client=ExistingRunKeeper(),
        execution_adapters=(),
        exact_base=BASE,
        now=NOW,
    )

    assert result["status"] == expected_status
    assert result["run_id"] == "run-existing"
    assert result["executor_session_id"] == "overnight-jules-remote"
    assert result["targeted_launch_count"] == 0
    assert result["executor_wakes"] == []


def test_active_canonical_task_without_broker_run_fails_closed():
    class MissingRunKeeper:
        def task_run(self, _task_id):
            return {"schema_version": "limen.conduct_task_run.v1", "found": False}

    with pytest.raises(TaskExecutionError, match="active without a conduct run"):
        start_task_execution(
            _task(status="in_progress"),
            client=MissingRunKeeper(),
            execution_adapters=(),
            exact_base=BASE,
            now=NOW,
        )


class BindingRemoteKeeper:
    def __init__(self):
        self.packet = None
        self.executor_session_id = ""

    def register(self, session):
        payload = session.model_dump(mode="json")
        if "conduct" in session.capabilities:
            payload["identity"]["agent"] = "codex"
            payload["identity"]["surface"] = "credential-bound-conductor"
        else:
            payload["identity"]["agent"] = "runtime-renamed"
            payload["identity"]["surface"] = "credential-bound-executor"
            self.executor_session_id = session.session_id
        return payload

    def submit(self, packet):
        self.packet = packet
        return {
            "status": "reserved",
            "run_id": "run-1",
            "root_run_id": "run-1",
            "executor_session_id": packet.execution["executor_session_id"],
        }

    def graph(self, _root_run_id):
        return {
            "root_run_id": "run-1",
            "nodes": [
                {
                    "run_id": "run-1",
                    "status": "reserved",
                    "executor_session_id": self.packet.execution["executor_session_id"],
                    "packet": self.packet.model_dump(mode="json"),
                    "lease": {"lease_id": "lease-1", "generation": 1},
                }
            ],
        }


def test_renamed_capability_executor_is_visible_and_woken(monkeypatch):
    keeper = BindingRemoteKeeper()
    unavailable = FakeAdapter(eligible=False)
    unavailable.name = "temporarily-unavailable"
    healthy = FakeAdapter()
    wakes = []

    def fake_wake(root_run_id, lanes):
        wakes.append((root_run_id, tuple(lanes)))
        return [{"session_id": next(iter(lanes)), "adapter": healthy.name, "status": "woken"}]

    monkeypatch.setattr(task_execution, "wake_executor_workers", fake_wake)
    result = start_task_execution(
        _task(),
        client=keeper,
        execution_adapters=(unavailable, healthy),
        exact_base=BASE,
        now=NOW,
    )

    assert result["status"] == "launched"
    assert keeper.packet.preferred_agent == "jules"
    assert keeper.packet.execution["executor_session_id"] == keeper.executor_session_id
    assert wakes == [("run-1", (keeper.executor_session_id,))]
    assert result["unavailable_adapters"] == [
        {"adapter": "temporarily-unavailable", "reason": "owner repository is not reachable"}
    ]


def test_http_executor_requires_distinct_registered_credential(monkeypatch):
    monkeypatch.delenv("LIMEN_CONDUCT_TOKEN_FAKE", raising=False)
    conductor = HttpConductClient("https://conduct.example", "conductor-token")

    with pytest.raises(TaskExecutionError, match="LIMEN_CONDUCT_TOKEN_FAKE"):
        task_execution._executor_client(conductor, FakeAdapter())


def test_http_executor_rejects_conductor_credential_reuse(monkeypatch):
    monkeypatch.setenv("LIMEN_CONDUCT_TOKEN_FAKE", "same-token")
    conductor = HttpConductClient("https://conduct.example", "same-token")

    with pytest.raises(TaskExecutionError, match="distinct registered credential"):
        task_execution._executor_client(conductor, FakeAdapter())


def test_adapter_registration_failure_is_visible_without_blocking_healthy_peer(monkeypatch):
    keeper = BindingRemoteKeeper()
    failing = FakeAdapter()
    failing.name = "auth-needed"
    healthy = FakeAdapter()
    original_executor_client = task_execution._executor_client

    def fake_executor_client(conductor_client, adapter):
        if adapter is failing:
            raise TaskExecutionError("credential unavailable")
        return original_executor_client(conductor_client, adapter)

    monkeypatch.setattr(task_execution, "_executor_client", fake_executor_client)
    monkeypatch.setattr(
        task_execution,
        "wake_executor_workers",
        lambda _root_run_id, lanes: [{"session_id": next(iter(lanes)), "adapter": healthy.name, "status": "woken"}],
    )

    result = start_task_execution(
        _task(),
        client=keeper,
        execution_adapters=(failing, healthy),
        exact_base=BASE,
        now=NOW,
    )

    assert result["status"] == "launched"
    assert result["unavailable_adapters"] == [{"adapter": "auth-needed", "reason": "credential unavailable"}]
