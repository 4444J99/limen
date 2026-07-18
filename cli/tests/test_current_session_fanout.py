from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "current-session-fanout.py"


def _load():
    spec = importlib.util.spec_from_file_location("current_session_fanout", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _args(session: Path, min_codex_planners: int = 10) -> Namespace:
    return Namespace(
        session=str(session),
        min_codex_planners=min_codex_planners,
        executor_lanes="auto",
        include_contrib=True,
        allow_reset_spend=False,
        runway="2d",
    )


def test_current_session_fanout_extracts_full_plan_set_and_marks_duplicates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = tmp_path / "session.jsonl"
    prior_plan = "# Prior Product Plan\n\n## Summary\n- Build 1000 alpha omega products from every prompt.\n"
    assistant_plan = (
        "# Full-Fleet Overnight Plan\n\n"
        "## Summary\n"
        "- Use all fleet lanes, overnight dispatch, executor criteria, and no reset spend.\n"
    )
    newest_plan = (
        "# Newest Revenue Plan\n\n## Summary\n- Route money, SEO, lead, and sell-ready work to reachable lanes.\n"
    )
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:00:00Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "text": (
                                        "A previous agent produced the plan below to accomplish "
                                        "the user's task.\n\n"
                                        f"{prior_plan}"
                                    )
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:01:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": f"<proposed_plan>\n{assistant_plan}</proposed_plan>"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:02:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": f"<proposed_plan>\n{assistant_plan}</proposed_plan>"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:03:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": f"<proposed_plan>\n{newest_plan}</proposed_plan>"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    mod = _load()
    monkeypatch.setattr(
        mod,
        "lane_rows",
        lambda: [
            {
                "agent": "codex",
                "kind": "local-cli",
                "status": "active",
                "reachable": True,
                "remaining": 10,
                "detail": "test",
            },
            {
                "agent": "opencode",
                "kind": "local-cli",
                "status": "active",
                "reachable": True,
                "remaining": 10,
                "detail": "test",
            },
            {
                "agent": "warp",
                "kind": "paid-service",
                "status": "human-gated",
                "reachable": False,
                "remaining": 10,
                "detail": "WARP_API_KEY not set",
            },
        ],
    )
    monkeypatch.setattr(
        mod, "digest_blockers", lambda: [{"source": "digest", "item": "local gate", "impact": "does not stop global"}]
    )
    parent_started = int(mod.time.time()) - 10
    parent_deadline = parent_started + 172_800
    monkeypatch.setenv("LIMEN_WORKSTREAM_STARTED_EPOCH", str(parent_started))
    monkeypatch.setenv("LIMEN_WORKSTREAM_DEADLINE_EPOCH", str(parent_deadline))

    snap = mod.build_snapshot(_args(session))

    assert snap["status"] == "ready"
    assert snap["plan_event_count"] == 4
    assert snap["unique_plan_count"] == 3
    assert snap["duplicate_plan_count"] == 1
    assert snap["unconsolidated_plan_hashes"] == []
    assert [event["title"] for event in snap["plan_events"]] == [
        "Newest Revenue Plan",
        "Full-Fleet Overnight Plan",
        "Full-Fleet Overnight Plan",
        "Prior Product Plan",
    ]
    assert snap["plan_events"][2]["duplicate"] is True
    assert "full-fleet-overnight" in snap["themes"]
    expected_plan_hashes = [event["hash"] for event in snap["unique_plan_sources"]]
    assert len(snap["planner_packets"]) >= 10
    assert {packet["target_agent"] for packet in snap["planner_packets"]} == {"codex"}
    assert {packet["target_agent"] for packet in snap["executor_packets"]} == {"opencode"}
    assert snap["workstream_contract"]["runway"]["duration_seconds"] == 172_800
    assert snap["workstream_contract"]["runway"]["started_epoch"] == parent_started
    assert snap["workstream_contract"]["runway"]["deadline_epoch"] == parent_deadline
    assert snap["workstream_contract"]["authorization"]["mode"] == "full_non_destructive"
    assert snap["workstream_contract"]["authorization"]["approval_mode"] == "never"
    assert all(
        packet["workstream_contract"] == snap["workstream_contract"]
        for packet in snap["planner_packets"] + snap["executor_packets"]
    )
    assert all(
        packet["source_plan_hashes"] == expected_plan_hashes
        for packet in snap["planner_packets"] + snap["executor_packets"]
    )
    assert snap["global_product_selection"]["status"] == "active"
    assert any(blocker["item"] == "warp lane human-gated" for blocker in snap["blocked_local_work"])

    seed = mod.task_seed_specs(snap, repo="organvm/limen")
    executor_seed = next(spec for spec in seed if spec["packet_type"] == "executor_packet")
    assert "profile:runway-seconds:172800" in executor_seed["labels"]
    assert '"approval_mode":"never"' in executor_seed["context"]
    assert "proceed without confirmation for in-scope reversible work" in executor_seed["context"]

    from limen.models import Task
    from limen.provider_selection import execution_profile_for

    task = Task(**mod.task_model_payload(executor_seed))
    assert task.workstream_contract == snap["workstream_contract"]
    profile = execution_profile_for(task)
    assert profile.runway_seconds == 172_800


def test_current_session_fanout_emits_plan_02_executor_criteria_and_safe_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = tmp_path / "session.jsonl"
    raw_private = "RAW_PRIVATE_PLAN_BODY_SHOULD_NOT_APPEAR"
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-30T00:00:00Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "A previous agent produced the plan below to accomplish the user's task.\n\n"
                                "# Full-Fleet Overnight Autonomy Fix\n\n"
                                "## Summary\n"
                                "- Build 1000 alpha omega products from the current session.\n"
                                f"- {raw_private}\n"
                                "- Everything means every fleet lane, all night, with local blockers recorded.\n"
                            )
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mod = _load()
    monkeypatch.setattr(
        mod,
        "lane_rows",
        lambda: [
            {
                "agent": "codex",
                "kind": "local-cli",
                "status": "active",
                "reachable": True,
                "remaining": 10,
                "detail": "test",
            },
            {
                "agent": "agy",
                "kind": "local-cli",
                "status": "active",
                "reachable": True,
                "remaining": 10,
                "detail": "test",
            },
            {
                "agent": "gemini",
                "kind": "local-cli",
                "status": "human-gated",
                "reachable": False,
                "remaining": 10,
                "detail": "gemini auth not configured",
            },
        ],
    )
    monkeypatch.setattr(mod, "digest_blockers", lambda: [])

    snap = mod.build_snapshot(_args(session, min_codex_planners=2))
    plan_02 = next(packet for packet in snap["planner_packets"] if packet["theme"] == "full-fleet-overnight")

    assert plan_02["id"] == "PLAN-02-ea38d4d8"
    assert plan_02["owner_packet"]["owner_repo"] == "organvm/limen"
    assert any("PAID_AGENT_ORDER" in item for item in plan_02["owner_packet"]["criteria"])
    assert any(
        "dispatch-async.py --lanes auto --dry-run" in item
        for item in plan_02["owner_packet"]["verification_predicates"]
    )
    assert snap["executor_packets"][0]["target_agent"] == "agy"
    assert snap["executor_packets"][0]["verification_predicates"]

    markdown = mod.render_markdown(snap)
    assert "## Plan Source Proof" in markdown
    assert "## Full-Fleet Overnight Owner Packet" in markdown
    assert "Executor criteria:" in markdown
    assert "Verification predicates:" in markdown
    assert "Global product selection remains `active`." in markdown
    assert "gemini lane human-gated" in markdown
    assert raw_private not in markdown
    assert raw_private in json.dumps(snap)


def test_parent_workstream_timing_rejects_inconsistent_runway(monkeypatch) -> None:
    mod = _load()
    parent_started = int(mod.time.time()) - 10
    monkeypatch.setenv("LIMEN_WORKSTREAM_STARTED_EPOCH", str(parent_started))
    monkeypatch.setenv("LIMEN_WORKSTREAM_DEADLINE_EPOCH", str(parent_started + 172_800))

    with pytest.raises(mod.ContractError, match="timing"):
        mod.admitted_packet_contract("1d")


def test_current_session_fanout_uses_registry_lanes_and_rejects_unbounded_runway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-17T00:00:00Z",
                "payload": {"type": "user_message", "message": "Conduct this session across the fleet."},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mod = _load()
    monkeypatch.setattr(mod, "PAID_AGENT_ORDER", ("codex", "jules", "agy", "opencode", "copilot"))
    rows = [
        {
            "agent": agent,
            "kind": "test",
            "status": "active",
            "reachable": True,
            "remaining": 3,
            "detail": "live registry",
        }
        for agent in ("codex", "jules", "agy", "opencode", "copilot")
    ]
    assert mod.lane_selection("auto", rows) == ["codex", "jules", "agy", "opencode", "copilot"]
    assert mod.lane_selection("auto", []) == []

    monkeypatch.setattr(mod, "lane_rows", lambda: rows)
    monkeypatch.setattr(mod, "digest_blockers", lambda: [])
    args = _args(session, min_codex_planners=1)
    args.runway = "forever"
    with pytest.raises(mod.ContractError):
        mod.build_snapshot(args)
