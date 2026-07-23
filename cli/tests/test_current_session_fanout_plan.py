from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "current-session-fanout-plan.py"


def _load():
    spec = importlib.util.spec_from_file_location("current_session_fanout_plan", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _write_session(path: Path) -> None:
    rows = [
        {
            "timestamp": "2026-06-30T10:00:00Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-quota", "cwd": "/work/limen"},
        },
        {
            "timestamp": "2026-06-30T10:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "RAW_PRIVATE quota reset guard should derive per_agent_reset, "
                            "reserve, runway, and usage health."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-30T10:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "sed -n '1,220p' scripts/usage-telemetry.py cli/src/limen/dispatch.py"}
                ),
            },
        },
        {
            "timestamp": "2026-06-30T10:10:00Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-blocked", "cwd": "/work/limen"},
        },
        {
            "timestamp": "2026-06-30T10:10:01Z",
            "type": "event_msg",
            "payload": {"message": "Local work blocked by WARP_API_KEY permission and needs_human registry entry."},
        },
        {
            "timestamp": "2026-06-30T10:20:00Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-product", "cwd": "/work/limen"},
        },
        {
            "timestamp": "2026-06-30T10:20:01Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {
                        "cmd": (
                            "LIMEN_DISCOVER_REPOS=organvm/limen python3 scripts/discover-value.py --floor 1 --max-new 1"
                        )
                    }
                ),
            },
        },
        {
            "timestamp": "2026-06-30T10:20:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Keep global product selection active."}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_plan_uses_full_session_not_latest_turn(tmp_path: Path) -> None:
    mod = _load()
    session = tmp_path / "session.jsonl"
    _write_session(session)

    snapshot = mod.build_snapshot(session, "PLAN-07-test", "quota-reset-guard")
    packets = {packet["theme"]: packet for packet in snapshot["owner_packets"]}

    assert snapshot["coverage"]["turn_contexts"] == 3
    assert snapshot["coverage"]["turns_scanned"] == 3
    assert snapshot["coverage"]["full_session_derived"] is True
    assert "turn-quota" in packets["quota-reset-guard"]["evidence_turns"]
    assert "turn-product" in packets["global-product-selection"]["evidence_turns"]
    assert packets["global-product-selection"]["depends_on_blocked_local_work"] is False


def test_plan_emits_criteria_predicates_and_redacts_text(tmp_path: Path) -> None:
    mod = _load()
    session = tmp_path / "session.jsonl"
    _write_session(session)
    mod.DOC_DIR = tmp_path / "docs" / "current-session-fanout"
    mod.PRIVATE_DIR = tmp_path / ".limen-private" / "session-corpus" / "lifecycle" / "current-session-fanout"

    snapshot = mod.build_snapshot(
        session,
        "PLAN-07-test",
        "quota-reset-guard",
        source_plan_hashes=["planhash1234"],
        source_prompt_hashes=["prompthash1234567890"],
    )
    markdown = mod.render_markdown(snapshot)
    doc_path, private_path = mod.write_outputs(snapshot, markdown)

    assert snapshot["coverage"]["packets_with_executor_criteria"] == 3
    assert snapshot["coverage"]["packets_with_verification_predicates"] == 3
    assert snapshot["coverage"]["blocked_local_packets"] == 1
    assert snapshot["coverage"]["global_product_selection_unblocked"] is True
    assert "Verification predicates" in markdown
    assert "Executor criteria" in markdown
    assert "RAW_PRIVATE" not in markdown
    assert "RAW_PRIVATE" not in private_path.read_text()
    assert doc_path.exists()
    assert private_path.exists()


def test_private_sauce_boundary_emits_theme_specific_packets(tmp_path: Path) -> None:
    mod = _load()
    session = tmp_path / "session.jsonl"
    rows = [
        {
            "timestamp": "2026-06-30T11:00:00Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-private", "cwd": "/work/limen"},
        },
        {
            "timestamp": "2026-06-30T11:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "RAW_PRIVATE private sauce must stay hidden while public-safe "
                            "fanout uses hashes and redaction."
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-06-30T11:01:00Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-blocker", "cwd": "/work/limen"},
        },
        {
            "timestamp": "2026-06-30T11:01:01Z",
            "type": "event_msg",
            "payload": {"message": "Local credential blocker recorded; product selection stays active."},
        },
    ]
    session.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    snapshot = mod.build_snapshot(
        session,
        "PLAN-10-test",
        "private-sauce-boundary",
        source_plan_hashes=["planhash1234"],
        source_prompt_hashes=["prompthash1234567890"],
    )
    packet_ids = {packet["id"] for packet in snapshot["owner_packets"]}
    markdown = mod.render_markdown(snapshot)

    assert snapshot["coverage"]["owner_packets"] == 4
    assert snapshot["coverage"]["packets_with_executor_criteria"] == 4
    assert snapshot["coverage"]["packets_with_verification_predicates"] == 4
    assert snapshot["coverage"]["blocked_local_packets"] == 1
    assert snapshot["coverage"]["global_product_selection_unblocked"] is True
    assert "PLAN-10-test-private-material-boundary" in packet_ids
    assert "PLAN-10-test-public-redaction-contract" in packet_ids
    assert "PLAN-10-test-outward-stage-gate" in packet_ids
    assert "RAW_PRIVATE" not in markdown
    assert "private-sauce-boundary" in markdown
    assert "raw session material stays in the ignored private corpus" in markdown
