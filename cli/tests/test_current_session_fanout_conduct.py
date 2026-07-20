from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from limen.conduct import AgentIdentityV1, ConductorSessionV1
from limen.conduct.client import LocalConductClient


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "current-session-fanout.py"


def _load():
    spec = importlib.util.spec_from_file_location("current_session_fanout_conduct", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _snapshot() -> dict[str, Any]:
    proposed_root = "proposed-root"
    proposed_planner = f"{proposed_root}/plan/01"
    return {
        "status": "ready",
        "session_hash": "a" * 24,
        "session_source": {"agent": "claude", "session_id": "native-session"},
        "initiator_agent": "claude",
        "conductor_agent": "codex",
        "root_run_id": proposed_root,
        "planner_packets": [
            {
                "id": "PLAN-01",
                "packet_type": "planner_packet",
                "target_agent": "codex",
                "theme": "current-session-intake",
                "worktree_slug": "planner-current-session",
                "root_run_id": proposed_root,
                "parent_run_id": proposed_root,
                "run_id": proposed_planner,
                "runtime_env": {"LIMEN_RUN_ID": proposed_planner},
                "source_prompt_hashes": ["prompt-hash"],
                "source_plan_hashes": ["plan-hash"],
                "owner_packet": {
                    "owner_repo": "organvm/limen",
                    "owner_ledger": "docs/current-session-fanout.md",
                },
                "acceptance": ["derive one bounded executor packet"],
                "executor_criteria": ["reserve before launch"],
                "verification_predicates": ["python3 -m py_compile scripts/current-session-fanout.py"],
            }
        ],
        "executor_packets": [
            {
                "id": "EXEC-01",
                "packet_type": "executor_packet",
                "target_agent": "opencode",
                "theme": "current-session-intake",
                "root_run_id": proposed_root,
                "parent_run_id": proposed_planner,
                "run_id": f"{proposed_root}/execute/opencode",
                "runtime_env": {"LIMEN_RUN_ID": f"{proposed_root}/execute/opencode"},
                "source_prompt_hashes": ["prompt-hash"],
                "source_plan_hashes": ["plan-hash"],
                "owner_packet": {
                    "owner_repo": "organvm/limen",
                    "owner_ledger": "docs/current-session-fanout.md",
                },
                "acceptance": ["bounded reversible work only"],
                "executor_criteria": ["reserve before launch"],
                "verification_predicates": ["python3 -m py_compile scripts/current-session-fanout.py"],
            }
        ],
    }


class FakeConductClient:
    def __init__(self, *, busy_at: int | None = None, capabilities_error: Exception | None = None):
        self.busy_at = busy_at
        self.capabilities_error = capabilities_error
        self.calls: list[tuple[Any, ...]] = []
        self.cancels: list[tuple[str, str]] = []
        self.reservation_number = 0

    def capabilities(self) -> dict[str, Any]:
        self.calls.append(("capabilities", None))
        if self.capabilities_error:
            raise self.capabilities_error
        return {
            "sessions": [
                {
                    "session_id": "conductor-session",
                    "identity": {
                        "schema_version": "limen.agent_identity.v1",
                        "agent": "codex",
                        "surface": "cli",
                        "session_id": "conductor-session",
                        "native_run_id": "native-conductor",
                    },
                    "capabilities": ["conduct", "execute"],
                    "healthy": True,
                    "accepting_work": True,
                    "active_leases": 0,
                }
            ]
        }

    def _reserve(self, operation: str, parent: str | None, packet: Any) -> dict[str, Any]:
        self.reservation_number += 1
        self.calls.append((operation, parent, packet))
        if self.busy_at == self.reservation_number:
            return {
                "schema_version": "limen.conduct_submit_result.v1",
                "status": "busy",
                "busy_receipt_id": f"busy-{self.reservation_number}",
            }
        run_id = ("run-root", "run-plan", "run-exec")[self.reservation_number - 1]
        executor_agent = ("codex", "codex", "opencode")[self.reservation_number - 1]
        generation = self.reservation_number
        return {
            "schema_version": "limen.conduct_submit_result.v1",
            "status": "reserved",
            "run_id": run_id,
            "root_run_id": "run-root",
            "executor_session_id": f"{executor_agent}-session",
            "capability_token": f"token-{generation}",
            "lease": {
                "lease_id": f"lease-{generation}",
                "generation": generation,
                "executor": {
                    "schema_version": "limen.agent_identity.v1",
                    "agent": executor_agent,
                    "surface": "cli",
                    "session_id": f"{executor_agent}-session",
                },
            },
        }

    def submit(self, packet: Any) -> dict[str, Any]:
        return self._reserve("submit", None, packet)

    def split(self, parent: str, packet: Any) -> dict[str, Any]:
        return self._reserve("split", parent, packet)

    def cancel(self, run_id: str, session_id: str) -> dict[str, Any]:
        self.cancels.append((run_id, session_id))
        return {"status": "cancelled", "run_id": run_id}


def test_live_fanout_reserves_root_planner_and_executor_before_exposing_child_envelopes() -> None:
    mod = _load()
    snapshot = _snapshot()
    client = FakeConductClient()

    result = mod.reserve_fanout(snapshot, client)

    assert result["status"] == "reserved"
    assert [call[0] for call in client.calls] == [
        "capabilities",
        "submit",
        "split",
        "split",
    ]
    assert client.calls[2][1] == "run-root"
    assert client.calls[3][1] == "run-plan"
    root_packet = client.calls[1][2]
    planner_packet = client.calls[2][2]
    executor_packet = client.calls[3][2]
    assert root_packet.parent_run_id is None
    assert planner_packet.root_run_id == "run-root"
    assert planner_packet.parent_run_id == "run-root"
    assert executor_packet.root_run_id == "run-root"
    assert executor_packet.parent_run_id == "run-plan"
    assert planner_packet.task_id == "CSF-AAAAAAAA-PLAN-01"
    assert executor_packet.task_id == "CSF-AAAAAAAA-EXEC-01"

    planner = snapshot["planner_packets"][0]
    executor = snapshot["executor_packets"][0]
    assert planner["runtime_env"] == {
        "LIMEN_AGENT": "codex",
        "LIMEN_INITIATOR_AGENT": "claude",
        "LIMEN_CONDUCTOR_AGENT": "codex",
        "LIMEN_ROOT_RUN_ID": "run-root",
        "LIMEN_PARENT_RUN_ID": "run-root",
        "LIMEN_RUN_ID": "run-plan",
        "LIMEN_TASK_ID": "CSF-AAAAAAAA-PLAN-01",
        "LIMEN_LEASE_ID": "lease-2",
        "LIMEN_LEASE_GENERATION": "2",
        "LIMEN_EXECUTION_HASH": planner_packet.execution_hash,
        "LIMEN_LEASE_TOKEN": "token-2",
    }
    assert executor["runtime_env"] == {
        "LIMEN_AGENT": "opencode",
        "LIMEN_INITIATOR_AGENT": "claude",
        "LIMEN_CONDUCTOR_AGENT": "codex",
        "LIMEN_ROOT_RUN_ID": "run-root",
        "LIMEN_PARENT_RUN_ID": "run-plan",
        "LIMEN_RUN_ID": "run-exec",
        "LIMEN_TASK_ID": "CSF-AAAAAAAA-EXEC-01",
        "LIMEN_LEASE_ID": "lease-3",
        "LIMEN_LEASE_GENERATION": "3",
        "LIMEN_EXECUTION_HASH": executor_packet.execution_hash,
        "LIMEN_LEASE_TOKEN": "token-3",
    }
    assert snapshot["conduct"]["root_runtime_env"]["LIMEN_LEASE_TOKEN"] == "token-1"
    assert "capability_token" not in snapshot["conduct"]["root"]
    rendered = mod.render_markdown(
        {
            **snapshot,
            "generated_at": "2026-07-18T00:00:00Z",
            "user_messages": 1,
            "prompt_bytes": 1,
            "themes": ["current-session-intake"],
            "plan_events": [],
            "no_reset_spend": True,
            "global_product_selection": {"status": "active"},
            "blocked_local_work": [],
            "task_seed": [],
        }
    )
    assert "token-" not in rendered


def test_busy_child_rolls_back_all_reserved_ancestors_without_exposing_lease_tokens() -> None:
    mod = _load()
    snapshot = _snapshot()
    proposed = deepcopy(snapshot)
    client = FakeConductClient(busy_at=3)

    with pytest.raises(mod.FanoutReservationError, match="failed closed: busy"):
        mod.reserve_fanout(snapshot, client)

    assert client.cancels == [
        ("run-plan", "conductor-session"),
        ("run-root", "conductor-session"),
    ]
    assert snapshot == proposed
    assert all(
        "LIMEN_LEASE_TOKEN" not in packet["runtime_env"]
        for packet in snapshot["planner_packets"] + snapshot["executor_packets"]
    )


def test_unavailable_broker_fails_before_submit_and_leaves_packets_unleased() -> None:
    mod = _load()
    snapshot = _snapshot()
    proposed = deepcopy(snapshot)
    client = FakeConductClient(capabilities_error=RuntimeError("offline"))

    with pytest.raises(mod.FanoutReservationError, match="unavailable during preflight.*offline"):
        mod.reserve_fanout(snapshot, client)

    assert client.calls == [("capabilities", None)]
    assert snapshot == proposed


def test_real_local_broker_accepts_the_reserved_three_level_graph(tmp_path: Path) -> None:
    mod = _load()
    client = LocalConductClient(tmp_path / "conduct.sqlite3")
    for agent, capabilities, concurrency in (
        ("codex", frozenset({"conduct", "execute"}), 4),
        ("opencode", frozenset({"execute"}), 2),
    ):
        identity = AgentIdentityV1(
            agent=agent,
            surface="test",
            session_id=f"{agent}-session",
        )
        client.register(
            ConductorSessionV1(
                session_id=identity.session_id,
                identity=identity,
                origin="direct",
                capabilities=capabilities,
                concurrency=concurrency,
            )
        )

    snapshot = _snapshot()
    result = mod.reserve_fanout(snapshot, client)
    graph = client.graph(str(result["root"]["root_run_id"]))

    assert result["status"] == "reserved"
    assert len(graph["nodes"]) == 3
    assert {node["packet"]["depth"] for node in graph["nodes"]} == {0, 1, 2}
    assert snapshot["planner_packets"][0]["runtime_env"]["LIMEN_LEASE_GENERATION"]
    assert snapshot["executor_packets"][0]["runtime_env"]["LIMEN_EXECUTION_HASH"]
