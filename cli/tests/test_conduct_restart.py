from __future__ import annotations

from datetime import datetime, timedelta, timezone

from limen.conduct import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    ConductBroker,
    ResourceClaimV1,
    SQLiteStateStore,
    WorkPacketV1,
)
from limen.work_loan import WorkLoanV1


def test_broker_restart_reconstructs_graph_and_active_lease(tmp_path) -> None:
    now = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)
    path = tmp_path / "conduct.sqlite3"
    identity = AgentIdentityV1(agent="opencode", surface="cli", session_id="open-session")
    first = ConductBroker(SQLiteStateStore(path))
    first.register(
        ConductorSessionV1(
            session_id=identity.session_id,
            identity=identity,
            origin="dispatched",
            capabilities=frozenset({"code", "conduct"}),
            heartbeat_at=now,
        )
    )
    packet = WorkPacketV1(
        work_id="restart-work",
        work_key="restart-work",
        intent={"objective": "prove restart"},
        execution={"command": "pytest"},
        initiator=identity,
        conductor=identity,
        required_capabilities=frozenset({"code"}),
        resource_claims=(ResourceClaimV1(key="task/restart"),),
        predicate="pytest -q",
        receipt_target="github:organvm/limen:pull-request:restart-work",
        work_loan=WorkLoanV1(
            source_origin="system_debt",
            horizon="present",
            value_case="Prove conduct state restarts without losing the active lease",
            budget_cost=1,
            owner_surface="organvm/limen",
        ),
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"code"}),
            repositories=frozenset({"organvm/limen"}),
        ),
        deadline=now + timedelta(hours=1),
    )
    reserved = first.submit(packet, now=now)

    restarted = ConductBroker(SQLiteStateStore(path))
    duplicate = restarted.submit(packet, now=now)
    assert duplicate["status"] == "duplicate"
    assert duplicate["run_id"] == reserved["run_id"]
    graph = restarted.graph(reserved["run_id"])
    assert graph["nodes"][0]["lease_id"] == reserved["lease"]["lease_id"]
