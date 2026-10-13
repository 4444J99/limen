from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path

import pytest
from limen.conduct import ConductBroker, ConductorSessionV1, MemoryStateStore
from limen.conduct.broker import authority_attenuates
from limen.inventory_admission import admit_execution, InventoryAdmissionError

NOW = datetime(2026, 10, 10, tzinfo=UTC)
path = Path(__file__).resolve().parents[2] / "scripts/ops6-recovery-graph.py"
spec = importlib.util.spec_from_file_location("ops6_graph", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CHECKOUTS = dict(launcher_checkout="/retained/launcher", source_checkout="/retained/source")


def packets():
    return module.build_packets("native-session", NOW + timedelta(minutes=30), **CHECKOUTS)


def policy():
    return {
        "mode": "recovery",
        "approved_priorities": [
            {"outcome_id": "ops6", "enabled": True, "recovery": True, "work_keys": [module.WORK_KEY]}
        ],
    }


def test_packet_authority_serial_dependencies_and_exclusive_claims():
    root, a, b, c = packets()
    assert root.intent["kind"] == "fanout-root"
    assert root.work_key == module.WORK_KEY
    assert not root.resource_claims
    assert a.authority.external_effects == {module.DEPLOY}
    assert b.authority.external_effects == {module.HOSTED}
    assert a.effect == b.effect == "external"
    assert a.resource_claims[0].key == f"external/{module.DEPLOY}"
    assert a.resource_claims[0].mode == "exclusive"
    assert b.execution["dependencies"] == [a.work_id]
    assert c.execution["dependencies"] == [b.work_id]
    assert c.effect == "read" and not c.authority.external_effects
    for child in (a, b, c):
        assert authority_attenuates(child.authority, root.authority)
        assert child.deadline == root.deadline
        assert child.retry.max_attempts == 1
        assert child.authority.may_delegate is False
    assert a.execution["exact_base"] == module.LAUNCHER
    assert a.execution["runtime_source"] == module.SOURCE


def test_atomic_graph_reserves_exactly_120_minutes_and_defers_b_and_c():
    graph = packets()
    broker = ConductBroker(MemoryStateStore(), execution_policy=policy())
    broker.register(
        ConductorSessionV1(
            session_id="native-session",
            identity=graph[0].conductor,
            origin="direct",
            capabilities=frozenset({"conduct", "code", "read-verifier", "predicate-receipt"}),
            human_protected=True,
            concurrency=1,
            heartbeat_at=NOW,
        ),
        now=NOW,
    )
    result = broker.submit_graph(graph, now=NOW)
    assert result["status"] == "reserved"
    state = broker.store.snapshot()
    runs = list(state["runs"].values())
    assert len(runs) == 4
    assert sum(r["execution_admission"]["reserved_seconds"] for r in runs) == 7200
    assert len({r["execution_admission"]["attempt_deadline"] for r in runs}) == 1
    by_key = {r["packet"]["work_key"]: r for r in runs}
    assert by_key[graph[2].work_key]["status"] == "waiting"
    assert by_key[graph[3].work_key]["status"] == "waiting"
    extra = graph[3].model_dump(mode="json")
    with pytest.raises(InventoryAdmissionError, match="outcome_budget_exhausted"):
        admit_execution(policy(), state, extra, NOW, waiting=True)


def test_rejection_rolls_back_all_reservations():
    graph = packets()
    broker = ConductBroker(MemoryStateStore(), execution_policy={"mode": "recovery", "approved_priorities": []})
    broker.register(
        ConductorSessionV1(
            session_id="native-session",
            identity=graph[0].conductor,
            origin="direct",
            capabilities=frozenset({"conduct"}),
            heartbeat_at=NOW,
        ),
        now=NOW,
    )
    before = broker.store.snapshot()
    with pytest.raises(Exception, match="execution_priority_not_approved"):
        broker.submit_graph(graph, now=NOW)
    assert broker.store.snapshot() == before


@pytest.mark.parametrize(
    "change",
    [
        {"exhaustive": False},
        {"remaining_seconds": 5400},
        {"reserved_seconds": 1800},
        {"matching_run_ids": ["prior-run"]},
        {"limit_seconds": 14400},
    ],
)
def test_insufficient_or_unknown_allowance_creates_no_graph(change):
    class Client:
        def execution_allowance(self, key):
            return {
                "schema_version": "limen.execution_allowance.v1",
                "work_key": key,
                "exhaustive": True,
                "limit_seconds": 7200,
                "remaining_seconds": 7200,
                "reserved_seconds": 0,
                "matching_run_ids": [],
                **change,
            }

        def submit_graph(self, graph):
            pytest.fail("unproven allowance must not submit")

    with pytest.raises(ValueError, match="not_proven_available"):
        module.submit(Client(), "native-session", now=NOW, **CHECKOUTS)
